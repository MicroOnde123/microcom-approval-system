"""Conservative General Permission reuse policy; no historical data backfill."""
import hashlib
import json
from decimal import Decimal

from django.core import signing
from django.utils.translation import gettext_lazy as _

from .reference_namespaces import administration_code

BASELINE_ACTION = "PERMISSION_BASELINE"
BASELINE_SALT = "requests.permission.baseline.v1"
REASONS = {
    "unchanged": _("Earlier approvals remain valid. Resumed at the step that returned the request."),
    "information": _("Approval-relevant information changed. Approval restarted from the first step."),
    "workflow": _("The approval workflow or assignments changed. Approval restarted from the first step."),
    "evidence": _("Previous approval evidence is missing or unreliable. Approval restarted from the first step."),
}


def is_general_permission(request):
    return (request.request_type.code == administration_code()
            and request.request_type.is_permission_request
            and not request.request_type.requires_materials
            and not request.material_items.exists())


def approval_roster(request):
    return list(request.approvals.order_by("step_order", "pk").values(
        "id", "workflow_step_id", "step_order", "approver_user_id",
        "alternate_approver_user_id", "requires_stock_classification"))


def information(request):
    attachments = []
    reliable = True
    for attachment in request.attachments.order_by("pk"):
        digest = hashlib.sha256()
        try:
            with attachment.file.open("rb") as stream:
                for chunk in stream.chunks():
                    digest.update(chunk)
            content_hash = digest.hexdigest()
        except (OSError, ValueError, NotImplementedError):
            content_hash = None
            reliable = False
        attachments.append({"id": attachment.pk, "name": attachment.original_name,
                            "file": attachment.file.name, "sha256": content_hash,
                            "uploaded_by": attachment.uploaded_by_id})
    values = {key: getattr(request, key) for key in (
        "request_type_id", "submitted_by_id", "department_id", "request_for_department_id",
        "description", "amount", "date_needed", "metadata_json")}
    # Saving a DecimalField does not quantize the in-memory instance. Compare
    # its database-scale value so 12 and 12.00 represent the same approval scope.
    if request.amount is not None:
        values["amount"] = format(Decimal(str(request.amount)), ".2f")
    values["type_flags"] = {"permission": request.request_type.is_permission_request,
                            "materials": request.request_type.requires_materials,
                            "amount": request.request_type.requires_amount, "code": request.request_type.code,
                            "active": request.request_type.is_active}
    values["attachments"] = attachments
    # Use the same canonical representation for dates/decimals on every attempt.
    return json.loads(json.dumps(values, sort_keys=True, default=str)), reliable


def workflow_evidence(request, workflow):
    steps = []
    for step in workflow.steps.order_by("step_order"):
        approver = step.approver_user
        if not approver and step.approver_role:
            approver = request.request_for_department.user_set.filter(role=step.approver_role, is_active=True).first()
        alternate = step.alternate_approver_user
        steps.append({"id": step.pk, "order": step.step_order, "role": step.approver_role_id,
                      "configured_user": step.approver_user_id, "primary": approver.pk if approver else None,
                      "primary_active": bool(approver and approver.is_active),
                      "alternate": step.alternate_approver_user_id,
                      "alternate_active": bool(alternate and alternate.is_active),
                      "required": step.is_required, "stock": step.is_stock_review})
    return {"id": workflow.pk, "type": workflow.request_type_id, "department": workflow.department_id,
            "min_amount": str(workflow.min_amount), "max_amount": str(workflow.max_amount),
            "active": workflow.is_active, "steps": steps}


def record_baseline(request, workflow):
    if not is_general_permission(request):
        return
    content, reliable = information(request)
    evidence = {"version": 1, "request": request.pk, "information": content, "reliable": reliable,
                "workflow": workflow_evidence(request, workflow), "roster": approval_roster(request)}
    request.audit_logs.create(action=BASELINE_ACTION, performed_by=request.submitted_by,
                              comment=signing.dumps(evidence, salt=BASELINE_SALT, compress=True))


def record_description_change(request, user, previous):
    if previous != request.description and is_general_permission(request):
        request.audit_logs.create(action="PERMISSION_DESCRIPTION_CHANGED", performed_by=user,
            comment=json.dumps({"version": 1, "previous": previous, "updated": request.description}, ensure_ascii=False))


def resume_decision(request, workflow):
    baseline = request.audit_logs.filter(action=BASELINE_ACTION).order_by("-pk").first()
    if not baseline:
        return None, "evidence"
    try:
        evidence = signing.loads(baseline.comment, salt=BASELINE_SALT)
        if (evidence["version"] != 1 or evidence["request"] != request.pk or evidence["reliable"] is not True
                or not isinstance(evidence["information"], dict) or not isinstance(evidence["workflow"], dict)
                or not isinstance(evidence["roster"], list)):
            return None, "evidence"
        current, reliable = information(request)
        if not reliable:
            return None, "evidence"
        # Retain both descriptions in signed evidence; only this comparison
        # excludes them. Existing version-1 baselines remain signature-checked.
        previous = evidence["information"]
        if not isinstance(previous.get("description"), str):
            return None, "evidence"
        current_relevant = {key: value for key, value in current.items() if key != "description"}
        previous_relevant = {key: value for key, value in previous.items() if key != "description"}
        if current_relevant != previous_relevant or not is_general_permission(request):
            return None, "information"
        if workflow_evidence(request, workflow) != evidence["workflow"]:
            return None, "workflow"
        roster = approval_roster(request)
        if roster != evidence["roster"]:
            return None, "evidence"
        rows = list(request.approvals.order_by("step_order", "pk"))
        returned = [row for row in rows if row.status == "RETURNED"]
        if len(returned) != 1 or len({row.step_order for row in rows}) != len(rows):
            return None, "evidence"
        target = returned[0]
        for row in rows:
            expected = "APPROVED" if row.step_order < target.step_order else "PENDING" if row.step_order > target.step_order else "RETURNED"
            if row.status != expected:
                return None, "evidence"
            if expected != "PENDING" and (not row.acted_at or row.acted_by_id not in (row.approver_user_id, row.alternate_approver_user_id) or row.acted_by_id is None):
                return None, "evidence"
        # Reject malformed or manually altered chains even if a baseline was signed.
        steps = evidence["workflow"]["steps"]
        if len(steps) != len(rows) or any(
            step["id"] != row.workflow_step_id or step["order"] != row.step_order
            or step["primary"] != row.approver_user_id or step["alternate"] != row.alternate_approver_user_id
            or not step["primary_active"] or (step["alternate"] and not step["alternate_active"])
            for step, row in zip(steps, rows)):
            return None, "evidence"
        return target, "unchanged"
    except (signing.BadSignature, KeyError, TypeError, ValueError, AttributeError):
        return None, "evidence"
