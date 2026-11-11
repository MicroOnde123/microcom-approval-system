"""Default-off boundary; disabled navigation must not touch any new table."""
from functools import wraps
from django.conf import settings
from django.http import Http404
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from .permissions import request_scope

def enabled():
    return getattr(settings, 'ADJUSTED_INVOICE_STATEMENTS_ENABLED', False) is True

def require_enabled():
    if not enabled(): raise Http404

def gated(view):
    @wraps(view)
    def call(*args, **kwargs):
        require_enabled()
        return view(*args, **kwargs)
    return call

def authorize(user, invoice, action='view'):
    require_enabled()
    if not getattr(user, 'is_authenticated', False): raise PermissionDenied
    actor = get_user_model().objects.get(pk=user.pk)
    required = ['view_invoice', 'view_adjustedinvoicestatement']
    if action == 'issue': required.append('issue_adjustedinvoicestatement')
    if action == 'document': required.append('document_adjustedinvoicestatement')
    if not actor.is_active or not all(actor.has_perm('invoicing.'+p) for p in required): raise PermissionDenied
    if not request_scope(actor).filter(pk=invoice.request_id).exists(): raise PermissionDenied
    return actor

def navigation(user, invoice):
    if not enabled() or invoice.status != 'FINALIZED': return {}
    try: authorize(user, invoice)
    except PermissionDenied: return {}
    from .adjusted_services import reconciliation
    try:
        snapshot=reconciliation(invoice.pk,user)
    except (ValidationError,DatabaseError):
        return {'invoice_id':invoice.pk,'unavailable':True}
    return {'invoice_id': invoice.pk,'snapshot':snapshot,
            'statements':list(invoice.adjusted_statements.values('pk','number','issue_date'))}
