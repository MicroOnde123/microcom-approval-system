"""Owned, versioned material-entry drafts; only confirmation changes inventory."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from .models import MaterialEntryDraft, MaterialReceipt
from .entry_services import authorize, decode_token, receive_stock, lock_receipt_operation
from .entry_review import validate_review


def _validate_data(mode, data):
    if not isinstance(data, dict) or (mode == "new" and not isinstance(data.get("material", {}), dict)):
        raise ValidationError(_("Invalid draft data."))
    for key, value in data.items():
        if key == "material" and mode == "new":
            if any(not isinstance(v, (str, bool)) for v in value.values()):
                raise ValidationError(_("Invalid draft data."))
        elif not isinstance(value, str):
            raise ValidationError(_("Invalid draft data."))


def _owned_draft(user, draft_id):
    authorize(user)
    try:
        draft = MaterialEntryDraft.objects.filter(pk=draft_id, owner=user).first()
    except (ValueError, TypeError):
        draft = None
    if draft is None:
        raise ValidationError(_("Draft not found."))
    if decode_token(user, draft.mode, draft.signed_token) != draft.operation_token:
        raise ValidationError(_("Invalid draft receipt token."))
    return draft


def _locked_draft(user, draft_id):
    draft = _owned_draft(user, draft_id)
    lock_receipt_operation(draft.operation_token)
    return MaterialEntryDraft.objects.select_for_update().get(pk=draft.pk, owner=user)


@transaction.atomic
def create_draft(*, user, mode, token, data):
    authorize(user)
    if mode not in MaterialEntryDraft.Mode.values:
        raise ValidationError(_("Invalid material entry type."))
    operation = decode_token(user, mode, token)
    _validate_data(mode, data)
    lock_receipt_operation(operation)
    if MaterialReceipt.objects.filter(operation_token=operation).exists():
        raise ValidationError(_("This entry has already been finalized."))
    draft, created = MaterialEntryDraft.objects.get_or_create(operation_token=operation,
        defaults={"owner": user, "mode": mode, "signed_token": token, "data": data})
    if not created:
        if (draft.owner_id != user.pk or draft.mode != mode or draft.signed_token != token
                or draft.status != MaterialEntryDraft.Status.DRAFT or draft.data != data):
            raise ValidationError(_("A draft already exists for this entry. Resume it before saving changes."))
    return draft


@transaction.atomic
def update_draft(*, user, draft_id, version, data):
    draft = _locked_draft(user, draft_id)
    _validate_data(draft.mode, data)
    if draft.status != MaterialEntryDraft.Status.DRAFT:
        raise ValidationError(_("Draft not found or no longer editable."))
    if draft.version != version:
        # Retrying the immediately preceding identical save is safe, but cannot
        # overwrite a later edit or consume another version.
        if isinstance(version, int) and draft.version == version + 1 and draft.data == data:
            return draft
        raise ValidationError(_("This draft has changed. Reload it before saving again."))
    if draft.data != data:
        draft.data = data
        draft.version += 1
        draft.save(update_fields=["data", "version", "updated_at"])
    return draft


def get_draft(*, user, draft_id, allow_completed=False):
    draft = _owned_draft(user, draft_id)
    if draft.status != MaterialEntryDraft.Status.DRAFT and not (
            allow_completed and draft.status == MaterialEntryDraft.Status.COMPLETED):
        raise ValidationError(_("Draft not found or no longer editable."))
    return draft


def list_drafts(*, user):
    authorize(user)
    return MaterialEntryDraft.objects.filter(owner=user, status=MaterialEntryDraft.Status.DRAFT).order_by("-updated_at", "-pk")


@transaction.atomic
def cancel_draft(*, user, draft_id, version):
    draft = _locked_draft(user, draft_id)
    if draft.status == MaterialEntryDraft.Status.COMPLETED:
        raise ValidationError(_("Completed drafts cannot be cancelled."))
    if draft.status == MaterialEntryDraft.Status.CANCELLED:
        return draft, False
    if draft.version != version:
        raise ValidationError(_("This draft has changed. Reload it before cancelling."))
    draft.status = MaterialEntryDraft.Status.CANCELLED
    draft.version += 1
    draft.save(update_fields=["status", "version", "updated_at"])
    return draft, True


@transaction.atomic
def complete_draft(*, user, draft_id, version, arguments, review_proof):
    draft = _locked_draft(user, draft_id)
    if draft.status == MaterialEntryDraft.Status.CANCELLED:
        raise ValidationError(_("This draft was cancelled."))
    retry = draft.status == MaterialEntryDraft.Status.COMPLETED
    if not isinstance(version, int) or draft.version != version + (1 if retry else 0):
        raise ValidationError(_("This draft has changed. Verify the details again."))
    if arguments["user"].pk != user.pk:
        raise ValidationError(_("Invalid receipt owner."))
    if arguments["mode"] != draft.mode or arguments["token"] != draft.signed_token:
        raise ValidationError(_("Invalid draft receipt token."))
    validate_review(review_proof, arguments, draft_context={"id": draft.pk, "version": version})
    receipt, created = receive_stock(**arguments, draft_id=draft.pk)
    if retry:
        if receipt.pk != draft.receipt_id:
            raise ValidationError(_("Invalid draft receipt token."))
        return receipt, created
    draft.receipt = receipt
    draft.status = MaterialEntryDraft.Status.COMPLETED
    draft.version += 1
    draft.save(update_fields=["receipt", "status", "version", "updated_at"])
    return receipt, created
