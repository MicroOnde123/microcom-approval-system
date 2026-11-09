"""Ordered agent selections and submission evidence; no profile reads in documents."""
from copy import deepcopy
from uuid import uuid4
import unicodedata

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils import timezone

INTERNAL_KEYS = ("agent_attempts", "agent_current_attempt")


def display_name(user):
    return user.full_name.strip() or user.get_full_name().strip() or user.username


def validate_people(value):
    if not isinstance(value, list):
        raise ValidationError(_("Invalid person selection."))
    if len(value) > 10:
        raise ValidationError(_("Select at most 10 people."))
    result, ids, keys = [], set(), set()
    for item in value:
        if not isinstance(item, dict):
            raise ValidationError(_("Invalid person selection."))
        kind = item.get("kind")
        if kind == "user":
            pk = item.get("user_id")
            if type(pk) is not int or pk < 1 or pk > 9223372036854775807:
                raise ValidationError(_("Invalid person selection."))
            if pk in ids:
                raise ValidationError(_("This registered user is already selected."))
            ids.add(pk)
            result.append({"kind": "user", "user_id": pk})
        elif kind == "manual":
            row = {"kind": "manual"}
            key = item.get("key")
            if not isinstance(key, str) or not key or len(key) > 64 or key in keys:
                raise ValidationError(_("Invalid person selection."))
            keys.add(key)
            row["key"] = key
            for field in ("first_name", "surname"):
                name = item.get(field)
                if not isinstance(name, str) or not name.strip():
                    raise ValidationError(_("First name and surname are required."))
                name = name.strip()
                if len(name) > 255 or any(unicodedata.category(c).startswith("C") for c in name):
                    raise ValidationError(_("Enter a valid name of at most 255 characters."))
                row[field] = name
            row["full_name"] = row["first_name"] + " " + row["surname"]
            result.append(row)
        else:
            raise ValidationError(_("Invalid person selection."))
    users = {u.pk: u for u in get_user_model().objects.filter(pk__in=ids, is_active=True)}
    if len(users) != len(ids):
        raise ValidationError(_("A selected user is invalid or inactive. Remove or replace this person."))
    for order, row in enumerate(result):
        row["order"] = order
        if row["kind"] == "user":
            row["full_name"] = display_name(users[row["user_id"]])
    return result


def prepare_submission(request):
    from .site_selection import prepare_sites
    prepare_sites(request)
    metadata = deepcopy(request.metadata_json or {})
    if metadata.get("permission_group") != "SITE_AUTHORIZATION" or not request.request_type.is_permission_request:
        return
    if "agent_selections" not in metadata:
        return  # Historical text is evidence; never guess identities.
    people = validate_people(metadata["agent_selections"])
    if not people:
        raise ValidationError(_("Select at least one person."))
    metadata["agent_selections"] = people
    metadata["microcom_agents"] = "; ".join(p["full_name"] for p in people)
    request.metadata_json = metadata
    request.save(update_fields=["metadata_json"])


def record_attempt(request):
    metadata = deepcopy(request.metadata_json or {})
    if metadata.get("permission_group") != "SITE_AUTHORIZATION" or not request.request_type.is_permission_request:
        return
    attempt_id = str(uuid4())
    attempt = {"id": attempt_id, "version": 2,
               "submitted_at": timezone.now().isoformat(), "submitted_by_id": request.submitted_by_id,
               "people": deepcopy(metadata.get("agent_selections")),
               "text": metadata.get("microcom_agents", ""),
               "sites": deepcopy(metadata.get("site_selections")),
               "site_text": metadata.get("site") or "",
               "approval_ids": list(request.approvals.order_by("step_order").values_list("pk", flat=True)),
               "archive_log_id": None}
    metadata.setdefault("agent_attempts", []).append(attempt)
    metadata["agent_current_attempt"] = attempt_id
    request.metadata_json = metadata
    request.save(update_fields=["metadata_json"])


def archive_attempt(request, log_id):
    metadata = deepcopy(request.metadata_json or {})
    current = metadata.get("agent_current_attempt")
    for attempt in metadata.get("agent_attempts", []):
        if attempt["id"] == current and attempt["archive_log_id"] is None:
            attempt["archive_log_id"] = log_id
            request.metadata_json = metadata
            request.save(update_fields=["metadata_json"])
            return


def rendered_names(request):
    metadata = request.metadata_json or {}
    if metadata.get("permission_group") != "SITE_AUTHORIZATION":
        return ""
    if request.status not in ("DRAFT", "RETURNED"):
        current = metadata.get("agent_current_attempt")
        for attempt in metadata.get("agent_attempts", []):
            if attempt["id"] == current:
                return attempt["text"]
    return metadata.get("microcom_agents", "")


def archived_names(request, archive_log_id):
    """A direct ID association, independent of audit comment formats."""
    for attempt in (request.metadata_json or {}).get("agent_attempts", []):
        if attempt.get("archive_log_id") == archive_log_id:
            return attempt["text"]
    return ""
