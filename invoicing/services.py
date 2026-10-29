"""Authorized invoice lifecycle. Financial writes only; stock evidence is read."""
import base64
import hashlib
import json
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils.translation import gettext as _

from core.document_config import Currency, validate_logo_reference
from core.models import CompanyDocumentSettings
from inventory.models import Material, Succursale
from requests_app.models import Request, StockMovement
from .configuration import business_date, configuration_digest
from .models import (CompanyVerification, DocumentSequence, Invoice, InvoiceLine,
    InvoiceIssueAllocation, InvoiceReturnExclusion, InvoiceAuditEvent)
from .permissions import authorize
from .words import amount_in_french

CENT = Decimal("0.01")
REVISION_SALT = "invoicing.draft_revision.v1"
logger = logging.getLogger(__name__)

# Exact static messages only: never put a driver's message/detail/context in logs.
_INTEGRITY_GUARDS = {
    "Financial document writes require READ COMMITTED isolation": "document_isolation",
    "Finalized financial documents are immutable": "finalized_document_immutable",
    "Document business timezone must match explicit company configuration": "company_timezone",
    "Approved Microcom request and classification confirmation required": "classification_evidence",
    "Financial allocation blocked: ambiguous or inconsistent stock history; administrator review required": "stock_provenance",
    "Company snapshot must match the verified configuration": "company_snapshot",
    "Company verification is stale": "company_verification_stale",
    "Complete priced invoice allocations and consistent totals required": "invoice_line_totals",
    "All pre-invoice returns must be excluded from billing": "return_exclusions",
    "Financial documents must begin as drafts": "initial_draft_required",
    "Verified document sequence required": "sequence_verification",
    "Backdated or future finalization is prohibited": "finalization_timestamp_window",
    "Current finalization time and complete immutable snapshots required": "finalization_snapshots_date",
    "Annual formats require the business year": "sequence_year_format",
    "Sequence counters cannot move backwards": "sequence_counter_backwards",
}


def _log_integrity_error(error):
    """Best-effort metadata only; diagnostic/logging failures must not mask errors."""
    def attribute(obj, name):
        try:
            return getattr(obj, name, None)
        except Exception:
            return None

    def token(value, pattern):
        return value if type(value) is str and re.fullmatch(pattern, value) else "unavailable"

    try:
        cause = attribute(error, "__cause__")
        original = error if cause is None else cause
        exception_class = token(type(original).__name__, r"[A-Za-z_][A-Za-z0-9_]{0,63}")
        sqlstate = "unavailable"
        for field in ("pgcode", "sqlstate"):
            sqlstate = token(attribute(original, field), r"[0-9A-Z]{5}")
            if sqlstate != "unavailable":
                break
        diag = attribute(original, "diag")
        constraint = token(attribute(diag, "constraint_name"), r"[A-Za-z_][A-Za-z0-9_$]{0,62}")
        primary = attribute(diag, "message_primary")
        guard = _INTEGRITY_GUARDS.get(primary, "unavailable") if type(primary) is str else "unavailable"
        logger.warning("Financial integrity failure: exception_class=%s sqlstate=%s constraint=%s guard=%s",
            exception_class, sqlstate, constraint, guard)
    except Exception:
        # Never fall back to logging the exception, its attributes or a traceback.
        pass


def financial_transaction(function):
    @wraps(function)
    def execute(*args, **kwargs):
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except IntegrityError as error:
            _log_integrity_error(error)
            raise ValidationError(_("The invoice could not be saved safely. Reload it and ask an administrator to review its evidence or numbering configuration.")) from error
    return execute


def database_now():
    with connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        return cursor.fetchone()[0]


def _configuration():
    try:
        configuration = CompanyDocumentSettings.objects.select_for_update().get(pk=1)
    except CompanyDocumentSettings.DoesNotExist:
        raise ValidationError(_("An administrator must configure and verify the company information first."))
    configuration.full_clean()
    if configuration.business_timezone!="Africa/Kinshasa":
        raise ValidationError(_("Invoice issuance requires the configured Africa/Kinshasa business timezone."))
    return configuration


def _verification(configuration):
    digest = configuration_digest(configuration)
    verification = CompanyVerification.objects.filter(configuration=configuration,content_digest=digest).order_by("-verified_at","-pk").first()
    if not verification or not verification.is_current:
        raise ValidationError(_("An administrator must verify the current company information before invoicing."))
    return verification


def _evidence(request):
    if request.status!="APPROVED" or not request.stock_deducted or not request.request_type.requires_materials:
        raise ValidationError(_("Only fully approved material requests with actual stock issuance can be invoiced."))
    if request.classification!="MICROCOM" or not request.succursale_id or not request.classified_by_id or not request.classified_at:
        raise ValidationError(_("A confirmed Microcom classification and succursale are required."))
    approvals = list(request.approvals.order_by("step_order","pk"))
    reviews = [approval for approval in approvals if approval.requires_stock_classification]
    if (len(reviews)!=1 or not approvals or reviews[0].pk!=approvals[0].pk or
            any(approval.status not in {"APPROVED","SKIPPED"} for approval in approvals) or
            reviews[0].status!="APPROVED" or not reviews[0].acted_at or reviews[0].acted_by_id!=request.classified_by_id):
        raise ValidationError(_("The designated first stock review must have confirmed this classification."))
    items = list(request.material_items.order_by("material_id","pk"))
    movements = list(StockMovement.objects.filter(request=request,movement_type__in=["OUT","RETURN"]).order_by("created_at","pk"))
    if not items or len({item.material_id for item in items})!=len(items):
        raise ValidationError(_("Financial allocation is ambiguous. Ask an administrator to review duplicate or missing material lines."))
    materials = {item.material_id for item in items}
    if any(movement.material_id not in materials for movement in movements):
        raise ValidationError(_("Stock movement relationships are inconsistent. Administrator review is required."))
    result = []
    for item in items:
        outs = [movement for movement in movements if movement.material_id==item.material_id and movement.movement_type=="OUT"]
        returns = [movement for movement in movements if movement.material_id==item.material_id and movement.movement_type=="RETURN"]
        if (len(outs)!=1 or item.quantity<=0 or outs[0].quantity!=item.quantity or
                any(movement.quantity<=0 or movement.created_at<outs[0].created_at for movement in returns)):
            raise ValidationError(_("A unique positive OUT movement matching each material line is required. Administrator review is required."))
        returned = sum((movement.quantity for movement in returns),Decimal("0"))
        if returned>outs[0].quantity:
            raise ValidationError(_("Historical returns exceed the issued quantity. Administrator review is required."))
        result.append((item,outs[0],returns,outs[0].quantity-returned))
    return reviews[0],result


def _price(value):
    if value is None or value=="":
        return None
    if isinstance(value,(float,bool)):
        raise ValidationError(_("Enter an exact nonnegative unit price with at most four decimal places."))
    try:
        price = Decimal(value)
        InvoiceLine._meta.get_field("unit_price").clean(price,None)
    except (ValueError,TypeError,ArithmeticError,ValidationError):
        raise ValidationError(_("Enter an exact nonnegative unit price with at most four decimal places."))
    return price


def _line_total(quantity,price):
    return None if price is None else (quantity*price).quantize(CENT,rounding=ROUND_HALF_UP)


def _event(invoice,actor,kind,details):
    InvoiceAuditEvent.objects.create(invoice=invoice,actor=actor,event_type=kind,
        document_identifier=invoice.number or f"DRAFT:{invoice.pk}",details=details)


def _financial_state(invoice,lines=None):
    return {"note":invoice.audit_metadata.get("note",""),"lines":[
        [line.pk,str(line.quantity),None if line.unit_price is None else str(line.unit_price),line.currency]
        for line in (invoice.lines.order_by("pk") if lines is None else sorted(lines,key=lambda line:line.pk))]}


def draft_revision(invoice,user,*,lines=None):
    state = json.dumps(_financial_state(invoice,lines),sort_keys=True,separators=(",", ":"))
    return signing.dumps({"invoice":invoice.pk,"user":user.pk,"digest":hashlib.sha256(state.encode()).hexdigest()},salt=REVISION_SALT)


def _check_revision(invoice,user,revision):
    try:
        value = signing.loads(revision,salt=REVISION_SALT,max_age=7200)
        current = signing.loads(draft_revision(invoice,user),salt=REVISION_SALT)
        if value!=current:
            raise ValueError
    except (signing.BadSignature,ValueError,TypeError):
        raise ValidationError(_("This draft has changed or the form has expired. Reload it before continuing."))


def _locked_invoice(invoice_id,user,action):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    authorize(user,action,invoice.request_id)
    return invoice


def _require_draft(invoice):
    if invoice.status!="DRAFT":
        raise ValidationError(_("Finalized invoices are read-only."))


@financial_transaction
def create_draft(request_id,user,*,currency):
    request = Request.objects.select_for_update().get(pk=request_id)
    authorize(user,"add_invoice",request.pk)
    if currency not in Currency.values:
        raise ValidationError(_("Select a supported invoice currency."))
    if Invoice.objects.filter(request=request).exists():
        raise ValidationError(_("This request already has an invoice."))
    review,evidence = _evidence(request)
    configuration = _configuration()
    verification = _verification(configuration)
    invoice = Invoice.objects.create(request=request,succursale_id=request.succursale_id,
        currency=currency,created_by=user,business_timezone=configuration.business_timezone,
        company_verification=verification,classification_approval=review,
        classification_actor_id=request.classified_by_id,classification_at=request.classified_at)
    materials = {material.pk:material for material in Material.objects.select_for_update().filter(
        pk__in=[item.material_id for item,_,_,_ in evidence]).order_by("pk")}
    sources = []
    for position,(item,out,returns,net) in enumerate(evidence,1):
        material = materials[item.material_id]
        price = material.unit_price if material.currency==currency else None
        line = InvoiceLine.objects.create(invoice=invoice,material=material,material_code_snapshot=material.code,
            description_snapshot=material.name+(" — "+material.description if material.description else ""),
            unit_snapshot=material.unit,quantity=net,unit_price=price,currency=currency,
            line_total=_line_total(net,price),position=position)
        allocation = InvoiceIssueAllocation.objects.create(line=line,out_movement=out,quantity=net)
        for returned in returns:
            InvoiceReturnExclusion.objects.create(issue_allocation=allocation,return_movement=returned,quantity=returned.quantity)
        sources.append({"line":line.pk,"out":out.pk,"net":str(net),"excluded_returns":[m.pk for m in returns],
                        "price_source":"catalogue" if price is not None else "unknown","price":None if price is None else str(price)})
    _event(invoice,user,"DRAFT_CREATED",{"currency":currency,"lines":sources})
    return invoice


@financial_transaction
def edit_draft(invoice_id,user,*,prices,note,revision):
    invoice = _locked_invoice(invoice_id,user,"change_invoice")
    _require_draft(invoice)
    _check_revision(invoice,user,revision)
    request = Request.objects.select_for_update().get(pk=invoice.request_id)
    _evidence(request)
    lines = list(invoice.lines.order_by("pk"))
    if not isinstance(prices,dict) or set(prices)!={line.pk for line in lines} or not isinstance(note,str) or len(note)>2000:
        raise ValidationError(_("The submitted invoice lines or note are invalid. Reload the draft."))
    before = _financial_state(invoice)
    parsed = {pk:_price(value) for pk,value in prices.items()}
    for line in lines:
        line.unit_price = parsed[line.pk]
        line.line_total = _line_total(line.quantity,line.unit_price)
        line.save(update_fields=["unit_price","line_total"])
    invoice.audit_metadata = {**invoice.audit_metadata,"note":note.strip()}
    invoice.save(update_fields=["audit_metadata"])
    _event(invoice,user,"DRAFT_EDITED",{"before":before,"after":_financial_state(invoice)})
    return invoice


@financial_transaction
def refresh_draft(invoice_id,user,*,revision):
    invoice = _locked_invoice(invoice_id,user,"change_invoice")
    _require_draft(invoice)
    _check_revision(invoice,user,revision)
    request = Request.objects.select_for_update().get(pk=invoice.request_id)
    _,evidence = _evidence(request)
    lines = {line.material_id:line for line in invoice.lines.select_related("issue_allocation")}
    if set(lines)!={item.material_id for item,_,_,_ in evidence}:
        raise ValidationError(_("The source material identities changed. Administrator review is required."))
    before = _financial_state(invoice)
    for item,out,returns,net in evidence:
        line = lines[item.material_id]
        try:
            allocation = line.issue_allocation
        except InvoiceIssueAllocation.DoesNotExist:
            raise ValidationError(_("The invoice issue allocation is missing. Administrator review is required."))
        if allocation.out_movement_id!=out.pk:
            raise ValidationError(_("The source movement identities changed. Administrator review is required."))
        for exclusion in allocation.return_exclusions.all():
            exclusion.delete()
        line.quantity = net
        line.line_total = _line_total(net,line.unit_price)
        line.save(update_fields=["quantity","line_total"])
        allocation.quantity = net
        allocation.save(update_fields=["quantity"])
        for returned in returns:
            InvoiceReturnExclusion.objects.create(issue_allocation=allocation,return_movement=returned,quantity=returned.quantity)
    _event(invoice,user,"DRAFT_REFRESHED",{"before":before,"after":_financial_state(invoice)})
    return invoice


def _match_net(invoice,evidence):
    lines = {line.material_id:line for line in invoice.lines.select_related("issue_allocation")}
    if set(lines)!={item.material_id for item,_,_,_ in evidence}:
        raise ValidationError(_("The source material identities changed. Administrator review is required."))
    for item,out,returns,net in evidence:
        line = lines[item.material_id]
        try:
            allocation = line.issue_allocation
        except InvoiceIssueAllocation.DoesNotExist:
            raise ValidationError(_("The invoice issue allocation is missing. Administrator review is required."))
        excluded = {row.return_movement_id:row.quantity for row in allocation.return_exclusions.all()}
        if (line.quantity!=net or allocation.quantity!=net or allocation.out_movement_id!=out.pk or
                excluded!={movement.pk:movement.quantity for movement in returns}):
            raise ValidationError(_("Stock returns have changed the net quantities. Refresh and review the draft before finalizing."))
    return list(lines.values())


def _branding(configuration):
    reference = configuration.logo_reference
    if not reference:
        return {"version":1,"strategy":"no-logo"}
    validate_logo_reference(reference)
    found = finders.find(reference)
    if not found:
        raise ValidationError(_("The configured logo is unavailable. An administrator must review it."))
    path = Path(found)
    if path.is_symlink() or path.stat().st_size>2*1024*1024:
        raise ValidationError(_("The configured logo cannot be frozen safely. Administrator review is required."))
    content = path.read_bytes()
    mime = "image/png" if content.startswith(b"\x89PNG\r\n\x1a\n") else (
        "image/jpeg" if content.startswith(b"\xff\xd8\xff") else (
        "image/webp" if content[:4]==b"RIFF" and content[8:12]==b"WEBP" else None))
    if not mime:
        raise ValidationError(_("Use a supported PNG, JPEG or WebP company logo."))
    return {"version":1,"strategy":"embedded-content","content_type":mime,
        "sha256":hashlib.sha256(content).hexdigest(),"content_base64":base64.b64encode(content).decode("ascii")}


def _issuance_sequence(series,configuration):
    """Select and lock an explicitly configured annual scope; never create one."""
    day = business_date(database_now(),configuration.business_timezone)
    try:
        sequence = DocumentSequence.objects.select_for_update().get(document_type="INVOICE",year=day.year,series=series)
    except DocumentSequence.DoesNotExist:
        raise ValidationError(_("An administrator must configure and verify the invoice sequence for this business year and series."))
    if not sequence.is_verified:
        raise ValidationError(_("The invoice sequence requires administrator verification of external numbering history."))
    sequence.full_clean()
    moment = database_now()
    day = business_date(moment,configuration.business_timezone)
    if day.year!=sequence.year:
        raise ValidationError(_("The business year changed while waiting for numbering. Reload and try again; no number was consumed."))
    return sequence,moment,day


@financial_transaction
def finalize_invoice(invoice_id,user,*,series="MAIN",revision):
    invoice = _locked_invoice(invoice_id,user,"finalize_invoice")
    if invoice.status=="FINALIZED":
        return invoice
    _check_revision(invoice,user,revision)
    request = Request.objects.select_for_update().get(pk=invoice.request_id)
    review,evidence = _evidence(request)
    lines = _match_net(invoice,evidence)
    if invoice.currency not in Currency.values or any(line.currency!=invoice.currency for line in lines):
        raise ValidationError(_("All invoice lines must use the same supported currency."))
    if any(line.unit_price is None for line in lines):
        raise ValidationError(_("Enter an authorized unit price for every line. Explicit zero prices are allowed."))
    configuration = _configuration()
    verification = _verification(configuration)
    branch = Succursale.objects.select_for_update().get(pk=request.succursale_id)
    address = (branch.physical_address or "").strip()
    if not address:
        raise ValidationError(_("Enter the succursale physical address before finalizing this invoice."))
    materials = {material.pk:material for material in Material.objects.select_for_update().filter(
        pk__in=[line.material_id for line in lines]).order_by("pk")}
    total = Decimal("0.00")
    for line in lines:
        line.unit_price = _price(line.unit_price)
        line.line_total = _line_total(line.quantity,line.unit_price)
        material = materials[line.material_id]
        line.material_code_snapshot = material.code
        line.description_snapshot = material.name+(" — "+material.description if material.description else "")
        line.unit_snapshot = material.unit
        line.save(update_fields=["line_total","material_code_snapshot","description_snapshot","unit_snapshot"])
        total += line.line_total
    Invoice._meta.get_field("total").clean(total,invoice)
    invoice.total = total
    invoice.amount_words_fr = amount_in_french(total,invoice.currency)
    invoice.company_verification = verification
    invoice.company_snapshot = dict(verification.configuration_snapshot)
    invoice.succursale_snapshot = {"id":branch.pk,"code":branch.code,"name":branch.name,"physical_address":address}
    invoice.request_reference_snapshot = request.request_number
    invoice.branding_snapshot = _branding(configuration)
    invoice.classification_approval = review
    invoice.classification_actor_id = request.classified_by_id
    invoice.classification_at = request.classified_at
    invoice.business_timezone = configuration.business_timezone
    # Take the business date only after snapshots are prepared. The DB guard
    # independently stamps time and rejects any midnight/year-boundary mismatch.
    sequence,moment,day = _issuance_sequence(series,configuration)
    counter = sequence.next_counter
    if counter>=9223372036854775807:
        raise ValidationError(_("The document sequence has reached its supported limit. Administrator review is required."))
    invoice.number = sequence.number_format.format(number=counter,year=day.year)
    invoice.sequence = sequence
    invoice.sequence_counter = counter
    invoice.audit_metadata = {**invoice.audit_metadata,"sequence_snapshot":{
        "id":sequence.pk,"document_type":sequence.document_type,"series":sequence.series,
        "year":sequence.year,"number_format":sequence.number_format,"starting_value":sequence.starting_value,
        "counter":counter,"verified_by_id":sequence.verified_by_id,"verified_at":sequence.verified_at.isoformat(),
        "verification_digest":sequence.verification_digest,"verification_evidence":sequence.verification_evidence}}
    invoice.issue_date = day
    invoice.finalized_by = user
    invoice.finalized_at = moment
    invoice.status = "FINALIZED"
    sequence.next_counter = counter+1
    sequence.save(update_fields=["next_counter"])
    invoice.save(_finalize_at_statement_time=True)
    invoice.refresh_from_db()
    _event(invoice,user,"FINALIZED",{"number":invoice.number,"sequence":sequence.pk,"counter":counter,
        "total":str(total),"currency":invoice.currency,"business_timezone":invoice.business_timezone,
        "issue_date":invoice.issue_date.isoformat(),"company_verification":verification.pk})
    return invoice
