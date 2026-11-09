"""Site selections use the existing shared authorization-attempt evidence."""
from copy import deepcopy
import unicodedata
from uuid import uuid4

from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from core.models import Site


def validate_sites(value, *, lock=False):
    if not isinstance(value, list):
        raise ValidationError(_("Invalid site selection."))
    if len(value) > 5:
        raise ValidationError(_("Select at most 5 sites."))
    result, ids, keys = [], set(), set()
    for order, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValidationError(_("Invalid site selection."))
        if item.get("kind") == "site":
            pk = item.get("site_id")
            if type(pk) is not int or not 0 < pk <= 9223372036854775807:
                raise ValidationError(_("Invalid site selection."))
            if pk in ids:
                raise ValidationError(_("This directory site is already selected."))
            ids.add(pk)
            row = {"kind": "site", "site_id": pk}
        elif item.get("kind") == "manual":
            name, key = item.get("name"), item.get("key")
            if not isinstance(key, str) or not key or len(key) > 64 or key in keys:
                raise ValidationError(_("Invalid site selection."))
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255 or any(
                    unicodedata.category(c).startswith("C") for c in name):
                raise ValidationError(_("Enter a valid site name of at most 255 characters."))
            keys.add(key)
            row = {"kind": "manual", "key": key, "name": name.strip()}
        else:
            raise ValidationError(_("Invalid site selection."))
        row["order"] = order
        result.append(row)
    query = Site.objects.filter(pk__in=ids, is_active=True).order_by("pk")
    if lock:
        query = query.select_for_update()
    sites = dict(query.values_list("pk", "name"))
    if len(sites) != len(ids):
        raise ValidationError(_("A selected site is invalid or inactive. Remove or replace it."))
    for row in result:
        if row["kind"] == "site":
            row["name"] = sites[row["site_id"]]
    return result


def prepare_sites(request):
    metadata = deepcopy(request.metadata_json or {})
    if metadata.get("permission_group") != "SITE_AUTHORIZATION" or not request.request_type.is_permission_request:
        return
    if "site_selections" not in metadata:
        if not isinstance(metadata.get("site"), str) or not metadata["site"].strip():
            raise ValidationError(_("Select at least one site."))
        return  # Existing free text remains legacy evidence, without account/directory matching.
    sites = validate_sites(metadata["site_selections"], lock=True)
    if not sites:
        raise ValidationError(_("Select at least one site."))
    metadata["site_selections"] = sites
    metadata["site"] = "; ".join(row["name"] for row in sites)
    request.metadata_json = metadata
    request.save(update_fields=["metadata_json"])


def preserve_legacy_attempt_site(request, metadata):
    """Attach original signed site evidence to a pre-feature shared attempt once.

    This never guesses names from the edited request. Approval IDs bind the signed
    baseline to the same existing attempt; failed verification leaves it untouched.
    """
    current = metadata.get("agent_current_attempt")
    attempt = next((row for row in metadata.get("agent_attempts", []) if row["id"] == current), None)
    if attempt and "site_text" in attempt:
        return
    if not request.pk:
        return
    from .resubmission import BASELINE_ACTION, BASELINE_SALT
    baseline = request.audit_logs.filter(action=BASELINE_ACTION).order_by("-pk").first()
    if not baseline:
        return
    try:
        evidence = signing.loads(baseline.comment, salt=BASELINE_SALT)
        original = evidence["information"]["metadata_json"]
        if not isinstance(original, dict):
            return
        recorded_sites = original.get("site_selections")
        if recorded_sites is not None and (not isinstance(recorded_sites, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in recorded_sites)):
            return
        approval_ids = [row["id"] for row in evidence["roster"]]
        expected_ids = attempt["approval_ids"] if attempt else list(
            request.approvals.order_by("step_order", "pk").values_list("pk", flat=True))
        if (evidence["version"] == 1 and evidence["request"] == request.pk
                and approval_ids and approval_ids == expected_ids
                and original.get("permission_group") == "SITE_AUTHORIZATION"
                and isinstance(original.get("site"), str)):
            if attempt is None:
                # Pre-picker requests may have a signed baseline but no shared
                # attempt object. Retain that recorded evidence in the same
                # architecture, without resolving any legacy name to a directory.
                attempt = {"id": str(uuid4()), "version": 2,
                           "submitted_at": baseline.created_at.isoformat(),
                           "submitted_by_id": evidence["information"]["submitted_by_id"],
                           "people": deepcopy(original.get("agent_selections")),
                           "text": original.get("microcom_agents") or "",
                           "approval_ids": approval_ids, "archive_log_id": None}
                metadata.setdefault("agent_attempts", []).append(attempt)
                metadata["agent_current_attempt"] = attempt["id"]
            attempt["site_text"] = original["site"]
            attempt["sites"] = deepcopy(original.get("site_selections"))
    except (signing.BadSignature, KeyError, TypeError, ValueError, AttributeError):
        return


def site_names(request, archive_log_id=None):
    metadata = request.metadata_json or {}
    if archive_log_id is not None:
        snapshot = next((row for row in metadata.get("agent_attempts", [])
                         if row.get("archive_log_id") == archive_log_id), {})
        return [row["name"] for row in snapshot["sites"]] if snapshot.get("sites") is not None else (
            [snapshot["site_text"]] if snapshot.get("site_text") else [])
    if metadata.get("permission_group") != "SITE_AUTHORIZATION":
        return []
    if request.status not in ("DRAFT", "RETURNED"):
        current = metadata.get("agent_current_attempt")
        for row in metadata.get("agent_attempts", []):
            if row["id"] == current and "site_text" in row:
                return [site["name"] for site in row["sites"]] if row.get("sites") is not None else (
                    [row["site_text"]] if row["site_text"] else [])
    if "site_selections" in metadata:
        return [row["name"] for row in metadata["site_selections"]]
    return [metadata["site"]] if metadata.get("site") else []
