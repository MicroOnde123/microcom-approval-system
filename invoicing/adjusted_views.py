import io
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import DatabaseError
from django.http import FileResponse,Http404
from django.shortcuts import get_object_or_404,render,redirect
from django.utils.translation import gettext as _,get_language
from django.views.decorators.http import require_http_methods,require_POST
from .models import Invoice,AdjustedInvoiceStatement
from .adjusted_access import gated,authorize
from . import adjusted_services as service
from .adjusted_pdf import render as render_pdf
from .return_note_access import navigation as br_navigation

class PreviewForm(forms.Form):
    series=forms.CharField(max_length=30,initial='MAIN',label=_('Series'))

class IssueForm(forms.Form):
    confirmation=forms.CharField(widget=forms.HiddenInput)
    confirmed=forms.BooleanField(label=_('I have reviewed the included returns and adjusted values.'))

def _invoice(request,pk):
    invoice=get_object_or_404(Invoice,pk=pk);authorize(request.user,invoice)
    return invoice

def _error(request,invoice,error):
    message=error.messages if isinstance(error,ValidationError) else [_('The statement could not be verified. Review a fresh preview or contact an administrator.')]
    return render(request,'invoicing/adjusted/error.html',{'invoice':invoice,'errors':message},status=409)

@gated
@login_required
@require_http_methods(['GET','POST'])
def overview(request,invoice_id):
    invoice=_invoice(request,invoice_id)
    try:
        snapshot=service.reconciliation(invoice.pk,request.user)
        can_issue=True
        try:authorize(request.user,invoice,'issue')
        except PermissionDenied:can_issue=False
        form=PreviewForm(request.POST or None)
        if request.method=='POST':
            authorize(request.user,invoice,'issue')
            if form.is_valid():
                snapshot,confirmation=service.preview(invoice.pk,request.user,series=form.cleaned_data['series'])
                return render(request,'invoicing/adjusted/preview.html',{'invoice':invoice,'snapshot':snapshot,'form':IssueForm(initial={'confirmation':confirmation})})
        return render(request,'invoicing/adjusted/overview.html',{'invoice':invoice,'snapshot':snapshot,'can_read_br':bool(br_navigation(request.user,invoice=invoice).get('can_read')),'statements':invoice.adjusted_statements.all(),'form':form,'can_issue':can_issue})
    except (ValidationError,DatabaseError) as error:return _error(request,invoice,error)

@gated
@login_required
@require_POST
def issue(request,invoice_id):
    invoice=_invoice(request,invoice_id);authorize(request.user,invoice,'issue')
    form=IssueForm(request.POST)
    if not form.is_valid():return _error(request,invoice,ValidationError(_('Confirm a valid statement preview.')))
    try:statement=service.issue(invoice.pk,request.user,confirmation=form.cleaned_data['confirmation'])
    except (ValidationError,DatabaseError) as error:return _error(request,invoice,error)
    return redirect('invoicing:adjusted_detail',statement_id=statement.pk)

@gated
@login_required
def detail(request,statement_id):
    try:statement=service.get_statement(statement_id,request.user)
    except AdjustedInvoiceStatement.DoesNotExist:raise Http404
    can_document=True
    try:authorize(request.user,statement.invoice,'document')
    except PermissionDenied:can_document=False
    return render(request,'invoicing/adjusted/detail.html',{'statement':statement,'snapshot':statement.snapshot,'can_read_br':bool(br_navigation(request.user,invoice=statement.invoice).get('can_read')),'can_document':can_document})

@gated
@login_required
@require_POST
def document(request,statement_id,attachment=False):
    try:statement=service.get_statement(statement_id,request.user,document=True)
    except AdjustedInvoiceStatement.DoesNotExist:raise Http404
    language=(get_language() or 'en').split('-')[0]
    if language not in ('en','fr'):language='en'
    try:content=render_pdf(statement,language)
    except (ValidationError,ValueError,KeyError):return _error(request,statement.invoice,ValidationError(_('The frozen statement PDF could not be rendered.')))
    response=FileResponse(io.BytesIO(content),as_attachment=attachment,filename=f'adjusted-statement-{statement.pk}-{language}.pdf',content_type='application/pdf')
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff';response['Referrer-Policy']='no-referrer'
    return response
