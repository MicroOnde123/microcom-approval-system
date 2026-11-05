"""Read-only, escaped presentation of archived approval evidence."""
import json
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from .resubmission import REASONS


def readable_audit_logs(request):
    logs = list(request.audit_logs.all())
    for log in logs:
        log.display_comment = log.comment
        if log.action == "PERMISSION_DESCRIPTION_CHANGED":
            try:
                payload = json.loads(log.comment)
                if (payload.get("version") == 1 and isinstance(payload.get("previous"), str)
                        and isinstance(payload.get("updated"), str)):
                    log.display_comment = _("Description changed from %(previous)s to %(updated)s.") % payload
            except (TypeError, ValueError, AttributeError):
                pass
        if log.action == "RESUBMITTED":
            try:
                payload = json.loads(log.comment)
                if isinstance(payload, dict) and payload.get("version") == 1 and isinstance(payload.get("reason"), str):
                    log.display_comment = REASONS.get(payload["reason"], log.comment)
            except (TypeError, ValueError):
                pass
    return logs


def archive_rows(log):
    try:
        data = json.loads(log.comment)
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("approvals"), list):
            return [], {}
        rows = [row for row in data["approvals"] if isinstance(row, dict)
                and isinstance(row.get("status"), str) and isinstance(row.get("comment", ""), str)
                and type(row.get("step_order")) is int
                and all(row.get(key) is None or type(row.get(key)) is int
                        for key in ("acted_by_id", "approver_user_id", "alternate_approver_user_id"))]
        routing = data.get("routing")
        routing = dict(routing) if isinstance(routing, dict) else {}
        routing["people"] = data.get("people") if isinstance(data.get("people"), dict) else {}
        if not isinstance(routing.get("reason"), str): routing["reason"] = None
        return rows, routing
    except (ValueError, TypeError):
        return [], {}


def historical_participant(request, user):
    for log in request.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED"):
        rows, _routing = archive_rows(log)
        if any(user.pk in (row.get("approver_user_id"), row.get("alternate_approver_user_id"), row.get("acted_by_id")) for row in rows):
            return True
    return False


def iter_attempts(logs, user=None, filters=None):
    """Parse one archive at a time, without querying names or retaining history."""
    for log in logs:
        rows, routing = archive_rows(log)
        if user is not None:
            rows = [row for row in rows if row.get("acted_by_id") == user.pk
                    or (not row.get("acted_by_id") and row.get("approver_user_id") == user.pk and row.get("acted_at"))]
        if not rows:
            continue
        decisions = []
        for row in rows:
            actor = row.get("acted_by_id") or row.get("approver_user_id")
            try:
                acted_at = parse_datetime(row.get("acted_at") or "")
            except (ValueError, TypeError):
                acted_at = None
            status = row.get("status", "")
            if filters:
                from zoneinfo import ZoneInfo
                day = acted_at.astimezone(ZoneInfo("Africa/Kinshasa")).date() if acted_at and acted_at.tzinfo else None
                if (filters.get("action") and status != filters["action"]
                        or filters.get("date_from") and (not day or day < filters["date_from"])
                        or filters.get("date_to") and (not day or day > filters["date_to"])):
                    continue
            decisions.append({"step": row.get("step_order"), "actor_id": actor,
                              "recorded_actor": routing["people"].get(str(actor)),
                              "status": status, "label": dict((
                                  ("APPROVED", _("Approved")), ("RETURNED", _("Returned")),
                                  ("REJECTED", _("Rejected")), ("PENDING", _("Pending")),
                                  ("SKIPPED", _("Skipped")))).get(status, _("Not recorded")),
                              "comment": row.get("comment") or "", "acted_at": acted_at})
        if decisions:
            yield {"log": log, "decisions": decisions,
                   "reason": REASONS.get(routing.get("reason")), "step": routing.get("resumed_step")}


def hydrate_attempts(attempts):
    user_ids = {decision["actor_id"] for attempt in attempts for decision in attempt["decisions"]
                if type(decision["actor_id"]) is int and not isinstance(decision["recorded_actor"], str)}
    people = get_user_model().objects.in_bulk(user_ids)
    for attempt in attempts:
        for decision in attempt["decisions"]:
            actor = people.get(decision["actor_id"])
            recorded = decision["recorded_actor"]
            decision["actor"] = recorded if isinstance(recorded, str) else (actor.full_name or actor.username) if actor else _("Not recorded")
    return attempts


def readable_attempts(logs, user=None, filters=None):
    return hydrate_attempts(list(iter_attempts(logs, user, filters)))


def archived_attempt_page(logs, user, filters, number, per_page=25):
    """Exact pagination with bounded retained memory, including last-page fallback.

    Text JSON cannot safely be filtered/cast in SQL for all supported legacy
    archives. Count matches in a streaming pass, retaining at most two pages.
    Only the displayed page needs actor lookups and presentation hydration.
    """
    try:
        requested = int(number)
    except (TypeError, ValueError):
        requested = 1
    start = (requested - 1) * per_page
    selected, last_page, total = [], [], 0
    for attempt in iter_attempts(logs, user, filters):
        if total % per_page == 0:
            last_page = []
        last_page.append(attempt)
        if start <= total < start + per_page:
            selected.append(attempt)
        total += 1
    paginator = Paginator(range(total), per_page)
    page = paginator.get_page(number)
    page.object_list = hydrate_attempts(selected if page.number == requested else last_page)
    return page
