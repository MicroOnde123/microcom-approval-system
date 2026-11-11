"""Issue detached statements using the existing authoritative BR ledger."""
import hashlib
import json
from uuid import UUID, uuid4
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import connection, transaction, models
from django.utils.translation import gettext as _
from requests_app.models import Request
from .models import Invoice, DocumentSequence, AdjustedInvoiceStatement
from .adjusted_access import authorize, require_enabled
from .configuration import business_date
from .return_note_services import _coordinator
from .services import database_now

SALT='invoicing.adjusted-statement.v1'
MAX_AGE=900

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _outer():
    require_enabled()
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ValidationError(_('Adjusted statement services require their own outermost transaction.'))

def _locked(invoice_id,user,action):
    source=Invoice.objects.get(pk=invoice_id)
    authorize(user,source,action)
    _coordinator(source.pk)  # same advisory lock/order as BR and credit issuance
    invoice=Invoice.objects.select_for_update().get(pk=source.pk)
    Request.objects.select_for_update().get(pk=invoice.request_id)
    actor=authorize(user,invoice,action)
    if invoice.status!='FINALIZED': raise ValidationError(_('A finalized invoice is required.'))
    return invoice,actor

def _snapshot(invoice):
    # SQL calls inv_rn_validate(), then aggregates the already-valued BR ledger.
    # No repricing, stock returns, reservations or source-document writes.
    with connection.cursor() as c:
        c.execute('SELECT inv_as_snapshot(%s)',[invoice.pk])
        value=c.fetchone()[0]
    return json.loads(value) if isinstance(value,str) else value

def _state_key(snapshot):
    # Frozen invoice + immutable issued BR identities define the reconciliation.
    # IDs are sorted in PostgreSQL; issuer, preview token, series, timestamp text
    # formatting and PDF language are deliberately not part of its identity.
    with connection.cursor() as cursor:
        cursor.execute('SELECT inv_as_state_key(%s::jsonb)', [json.dumps(snapshot)])
        return cursor.fetchone()[0]


def _matching_statement(invoice, state_key):
    return AdjustedInvoiceStatement.objects.filter(invoice=invoice).annotate(
        reconciliation_key=models.Func(models.F('snapshot'), function='inv_as_state_key',
                                       output_field=models.CharField())
    ).filter(reconciliation_key=state_key).first()


def reconciliation(invoice_id,user):
    _outer()
    with transaction.atomic(durable=True):
        invoice,_actor=_locked(invoice_id,user,'view')
        return _snapshot(invoice)

def preview(invoice_id,user,*,series='MAIN'):
    _outer()
    if not isinstance(series,str) or not series.strip() or len(series)>30: raise ValidationError(_('Invalid statement series.'))
    with transaction.atomic(durable=True):
        invoice,actor=_locked(invoice_id,user,'issue')
        snapshot=_snapshot(invoice)
        if not snapshot['returns']: raise ValidationError(_('No issued return adjustment is available.'))
        binding={'invoice':invoice.pk,'actor':actor.pk,'series':series,'snapshot':digest(snapshot),'state':_state_key(snapshot),
                 'day':business_date(database_now(),invoice.business_timezone).isoformat(),'token':str(uuid4())}
        return snapshot,signing.dumps(binding,salt=SALT,compress=True)

def issue(invoice_id,user,*,confirmation):
    _outer()
    try:
        binding=signing.loads(confirmation,salt=SALT) # exact committed retry may outlive preview
        token=UUID(binding['token'])
    except (signing.BadSignature,ValueError,TypeError,KeyError):
        raise ValidationError(_('Invalid or expired statement confirmation.')) from None
    with transaction.atomic(durable=True):
        invoice,actor=_locked(invoice_id,user,'issue')
        if binding['invoice']!=invoice.pk or binding['actor']!=actor.pk: raise ValidationError(_('Invalid statement confirmation.'))
        existing=AdjustedInvoiceStatement.objects.filter(operation_token=token).first()
        if existing:
            if existing.invoice_id!=invoice.pk or existing.issued_by_id!=actor.pk or existing.confirmation_digest!=digest(confirmation):
                raise ValidationError(_('Invalid statement confirmation.'))
            return existing
        # A previously committed state is a read-only result, even if another
        # preview/actor originally issued it or further BRs now exist. Check
        # this before expiry/date/staleness rules, which govern new issuance.
        if binding.get('state'):
            matching = _matching_statement(invoice, binding['state'])
            if matching is not None:
                return matching
        try: signing.loads(confirmation,salt=SALT,max_age=MAX_AGE)
        except signing.BadSignature: raise ValidationError(_('Invalid or expired statement confirmation.')) from None
        snapshot=_snapshot(invoice)
        if not snapshot['returns'] or digest(snapshot)!=binding['snapshot']: raise ValidationError(_('Returns changed. Review a new statement preview.'))
        # Compatibility for signed previews created before state-key binding.
        matching = _matching_statement(invoice, _state_key(snapshot))
        if matching is not None:
            return matching
        day=business_date(database_now(),invoice.business_timezone)
        if day.isoformat()!=binding['day']: raise ValidationError(_('The business date changed. Review a new statement preview.'))
        try: seq=DocumentSequence.objects.select_for_update().get(document_type='ADJUSTED',year=day.year,series=binding['series'])
        except DocumentSequence.DoesNotExist: raise ValidationError(_('Configure and verify the adjusted statement sequence first.')) from None
        seq.full_clean()
        if not seq.is_verified: raise ValidationError(_('Verify the adjusted statement numbering history first.'))
        authorize(user,invoice,'issue')
        moment=database_now();day=business_date(moment,invoice.business_timezone)
        if day.isoformat()!=binding['day']: raise ValidationError(_('The business date changed. Review a new statement preview.'))
        counter=seq.next_counter
        if counter>=9223372036854775807: raise ValidationError(_('Statement numbering limit reached.'))
        number=seq.number_format.format(number=counter,year=day.year)
        seq.next_counter=counter+1;seq.save(update_fields=['next_counter'])
        statement=AdjustedInvoiceStatement.objects.create(invoice=invoice,sequence=seq,sequence_counter=counter,
            number=number,issued_at=moment,issue_date=day,issued_by=actor,issuer_name=actor.full_name or actor.username,
            operation_token=token,confirmation_digest=digest(confirmation),snapshot=snapshot)
        statement.refresh_from_db()
        return statement

def get_statement(statement_id,user,*,document=False):
    require_enabled()
    statement=AdjustedInvoiceStatement.objects.select_related('invoice').get(pk=statement_id)
    authorize(user,statement.invoice,'document' if document else 'view')
    return statement
