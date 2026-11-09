"""Transactional ordinary-request references and durable creation replay."""
import hashlib
import json
import re
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils.translation import gettext as _

from .models import RequestCreationReceipt, RequestType
from .reference_namespaces import validate_namespace_owner

MAX_COUNTER = 9223372036854775807
NAMESPACE = re.compile(r"[A-Z][A-Z0-9]{0,15}\Z")


def namespace_for(request_type):
    expected = validate_namespace_owner(request_type.code, request_type.reference_namespace)
    if request_type.reference_namespace:
        value = request_type.reference_namespace
    elif expected:
        value = expected
    else:
        value = re.sub(r"[^A-Z0-9]", "", request_type.code.upper())
        if len(value) > 16:
            value = value[:10] + hashlib.sha256(request_type.code.encode()).hexdigest()[:6].upper()
        if value in {"ADM", "MAT"}:
            raise ValidationError(_("This request type needs a distinct reference namespace. Ask an administrator."))
    if not NAMESPACE.fullmatch(value):
        raise ValidationError(_("This request type needs a valid reference namespace. Ask an administrator."))
    return value


def format_reference(namespace, year, counter):
    if not NAMESPACE.fullmatch(namespace) or not 1 <= year <= 9999 or not 1 <= counter <= MAX_COUNTER:
        raise ValidationError(_("The request reference is outside the supported range."))
    return f"REQ-{namespace}-{counter:04d}/{year}"


def creation_digest(post, files):
    """Bind actual submitted values and upload bytes, excluding transport tokens.

    Hash upload chunks without storing contents or consuming subsequent saves.
    """
    payload = {key: post.getlist(key) for key in sorted(post) if key not in {"csrfmiddlewaretoken", "submission_token"}}
    uploads = []
    for key in sorted(files):
        for upload in files.getlist(key):
            position = upload.tell()
            digest = hashlib.sha256()
            try:
                upload.seek(0)
                for chunk in upload.chunks():
                    digest.update(chunk)
            finally:
                upload.seek(position)
            uploads.append([key, upload.name, upload.size, upload.content_type, digest.hexdigest()])
    return hashlib.sha256(json.dumps([payload, uploads], sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _identity(token, digest):
    try:
        token = UUID(str(token))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(_("Invalid request creation confirmation.")) from None
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValidationError(_("Invalid request creation confirmation."))
    return token


def _replay(receipt, actor, digest):
    if receipt.actor_id != actor.pk or receipt.payload_digest != digest or not receipt.request_id:
        raise ValidationError(_("This confirmation was used for different request data. Open a new creation form."))
    return receipt.request


def committed_creation(token, actor, digest):
    token = _identity(token, digest)
    receipt = RequestCreationReceipt.objects.select_related("request").filter(token=token).first()
    return _replay(receipt, actor, digest) if receipt else None


def _allocate(request_type):
    if connection.vendor != "postgresql" or not connection.in_atomic_block:
        raise ValidationError(_("Request reference allocation requires a PostgreSQL transaction."))
    namespace = namespace_for(request_type)
    if not request_type.reference_namespace:
        if RequestType.objects.exclude(pk=request_type.pk).filter(reference_namespace=namespace).exists():
            raise ValidationError(_("This request type needs a distinct reference namespace. Ask an administrator."))
        request_type.reference_namespace = namespace
        request_type.save(update_fields=["reference_namespace"])
    # The type row is already locked: serialize first use as well as rollover.
    # One DB instant determines both the recorded allocation time and year.
    with connection.cursor() as cursor:
        cursor.execute("""
            WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS allocated_at),
            allocation AS (
                INSERT INTO requests_app_requestreferencesequence (request_type_id, year, last_counter)
                SELECT %s, extract(year FROM allocated_at AT TIME ZONE 'Africa/Kinshasa')::integer, 1 FROM instant
                ON CONFLICT (request_type_id, year) DO UPDATE
                SET last_counter = requests_app_requestreferencesequence.last_counter + 1
                WHERE requests_app_requestreferencesequence.last_counter < %s
                RETURNING year, last_counter
            ) SELECT allocation.year, allocation.last_counter, instant.allocated_at FROM allocation CROSS JOIN instant
        """, [request_type.pk, MAX_COUNTER])
        row = cursor.fetchone()
    if row is None:
        raise ValidationError(_("The request sequence is exhausted. Administrator review is required."))
    year, counter, allocated_at = row
    return namespace, year, counter, allocated_at


@transaction.atomic
def create_request_once(instance, actor, *, token, digest, save_related, submit, save_files=None):
    """Only creation enters here. All later lifecycle actions keep its reference."""
    token = _identity(token, digest)
    receipt, _created = RequestCreationReceipt.objects.get_or_create(
        token=token, defaults={"actor": actor, "payload_digest": digest})
    # The nullable request join must not itself be a FOR UPDATE target.
    receipt = RequestCreationReceipt.objects.select_for_update(of=("self",)).select_related("request").get(token=token)
    if receipt.request_id:
        return _replay(receipt, actor, digest), True
    if receipt.actor_id != actor.pk or receipt.payload_digest != digest:
        raise ValidationError(_("This confirmation was used for different request data. Open a new creation form."))
    if not instance._state.adding or not actor.is_active or not actor.department_id or instance.submitted_by_id != actor.pk:
        raise ValidationError(_("Invalid request creation confirmation."))
    request_type = RequestType.objects.select_for_update().get(pk=instance.request_type_id)
    namespace, year, counter, moment = _allocate(request_type)
    instance.request_number = format_reference(namespace, year, counter)
    instance.reference_namespace_snapshot, instance.reference_year = namespace, year
    instance.reference_counter, instance.reference_allocated_at = counter, moment
    instance.save()
    save_related(instance)
    if save_files:
        save_files(instance)
    if submit:
        from .services import submit_request
        try:
            submit_request(instance, notifications_on_commit=True)
        except ValidationError as error:
            raise ValidationError(_("No approval workflow is configured for this request type.")) from error
    receipt.request = instance
    receipt.save(update_fields=["request"])
    return instance, False
