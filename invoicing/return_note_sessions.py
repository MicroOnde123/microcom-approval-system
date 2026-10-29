"""Bounded server-side confirmation envelopes; no new session infrastructure."""
from copy import deepcopy
import math
import re
import time
from uuid import UUID, uuid4

from django.conf import settings

from .return_note_recovery import session_error

SESSION_KEY = "material_return_note_confirmations_v1"
MAX_HANDLES = 32
PREVIEW_AGE = 7200
SERVER_SESSIONS = {"django.contrib.sessions.backends.db", "django.contrib.sessions.backends.cached_db",
                   "django.contrib.sessions.backends.cache", "django.contrib.sessions.backends.file"}
HANDLE = re.compile(r"[0-9a-f]{32}\Z")
FIELDS = {"version", "created_at", "actor", "invoice", "arguments", "issuance_token", "confirmation"}


def _positive(value):
    return type(value) is int and 0 < value <= 9223372036854775807


def valid(entry, *, now=None):
    now = time.time() if now is None else now
    if not isinstance(entry, dict) or set(entry) != FIELDS or type(entry["version"]) is not int or entry["version"] != 2:
        return False
    created = entry["created_at"]
    if type(created) not in {int, float} or not 0 <= created <= now + 30 or not math.isfinite(created):
        return False
    if not _positive(entry["actor"]) or not _positive(entry["invoice"]):
        return False
    arguments = entry["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != {"return_movement_ids", "reason", "series"}:
        return False
    ids = arguments["return_movement_ids"]
    if not isinstance(ids, list) or not ids or any(not _positive(pk) for pk in ids) or len(set(ids)) != len(ids):
        return False
    for key, limit in [("reason", 2000), ("series", 30)]:
        value = arguments[key]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            return False
    token = entry["issuance_token"]
    try:
        if not isinstance(token, str) or str(UUID(token)) != token:
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    return isinstance(entry["confirmation"], str) and 0 < len(entry["confirmation"]) <= 16384


def entries(request):
    if settings.SESSION_ENGINE not in SERVER_SESSIONS:
        raise session_error()
    raw = request.session.get(SESSION_KEY, {})
    if not isinstance(raw, dict) or len(raw) > MAX_HANDLES:
        raise session_error()
    # Drop no persisted data here. Ignore invalid unrelated entries so one old
    # tab cannot crash another; loading a missing/invalid target fails closed.
    return {handle: deepcopy(value) for handle, value in raw.items()
            if isinstance(handle, str) and HANDLE.fullmatch(handle) and valid(value)}


def store(request, invoice_id, preview, arguments):
    pending = entries(request)
    entry = {"version": 2, "created_at": time.time(), "actor": request.user.pk, "invoice": invoice_id,
             "arguments": deepcopy(arguments), "issuance_token": preview.get("issuance_token"),
             "confirmation": preview.get("confirmation")}
    if not valid(entry):
        raise session_error()
    while len(pending) >= MAX_HANDLES:
        pending.pop(next(iter(pending)))
    handle = uuid4().hex
    pending[handle] = entry
    request.session[SESSION_KEY] = pending
    return handle


def load(request, invoice_id, handle):
    if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
        raise session_error()
    entry = entries(request).get(handle)
    if not entry or entry["actor"] != request.user.pk or entry["invoice"] != invoice_id:
        raise session_error()
    # Age is checked and reported, but MUST NOT preempt E-R2 exact committed
    # replay. E-R2 verifies the signed timestamp for every new issuance.
    return entry, time.time() - entry["created_at"] > PREVIEW_AGE
