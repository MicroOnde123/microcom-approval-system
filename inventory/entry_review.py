"""Read-only review proofs. The operation token remains the receipt identity."""
import hashlib
import json
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

REVIEW_SALT = "inventory.receipt_review.v1"


def service_arguments(user, mode, receipt_form, material_form):
    cleaned = receipt_form.cleaned_data
    return dict(user=user, mode=mode, token=cleaned["token"],
        receipt_data={k: v for k, v in cleaned.items() if k not in ("token", "material")},
        material_id=cleaned["material"].pk if mode == "existing" else None,
        material_data={k: (v.pk if k == "category" else v) for k, v in material_form.cleaned_data.items()} if mode == "new" else None)


def review_identity(arguments, *, draft_context=None):
    values = {key: value for key, value in arguments.items() if key != "user"}
    identity = {"user": arguments["user"].pk, "operation": arguments["token"],
            "payload": hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()}
    if draft_context is not None:
        identity["draft"] = draft_context
    return identity


def sign_review(arguments, *, draft_context=None):
    return signing.dumps(review_identity(arguments, draft_context=draft_context), salt=REVIEW_SALT, compress=True)


def validate_review(proof, arguments, *, draft_context=None):
    try:
        if signing.loads(proof, salt=REVIEW_SALT) != review_identity(arguments, draft_context=draft_context):
            raise ValueError
    except (signing.BadSignature, TypeError, ValueError):
        raise ValidationError(_("The reviewed details have changed or are invalid. Verify the details again before confirming."))
