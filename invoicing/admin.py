from .adjusted_access import enabled as adjusted_statements_enabled
"""Financial records are viewed here; all lifecycle mutations use authorized services."""
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext_lazy as _

from .models import CompanyVerification, DocumentSequence, Invoice
from .permissions import request_scope


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id","number","status","currency","total","created_at")
    readonly_fields = tuple(field.name for field in Invoice._meta.concrete_fields)

    def get_queryset(self,request):
        return super().get_queryset(request).filter(request_id__in=request_scope(request.user).values("pk"))

    def has_view_permission(self,request,obj=None):
        return bool(request.user.is_active and request.user.has_perm("invoicing.view_invoice") and
            (obj is None or request_scope(request.user).filter(pk=obj.request_id).exists()))

    def has_add_permission(self,request):
        return False

    def has_change_permission(self,request,obj=None):
        return False

    def has_delete_permission(self,request,obj=None):
        return False


class SequenceForm(forms.ModelForm):
    class Meta:
        model = DocumentSequence
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        starting = cleaned.get("starting_value")
        if starting is not None:
            self.instance.next_counter = max(self.instance.next_counter,starting)
        return cleaned


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    form = SequenceForm
    list_display = ("document_type","year","series","starting_value","next_counter","verified_at")
    readonly_fields = ("next_counter","verified_by","verified_at","verification_digest")
    actions = ("verify_numbering_history",)

    def get_readonly_fields(self,request,obj=None):
        result = list(self.readonly_fields)
        if obj and (obj.invoice_documents.filter(status="FINALIZED").exists() or obj.creditnote_documents.filter(status="FINALIZED").exists() or obj.materialreturnnote_documents.filter(status="FINALIZED").exists() or (adjusted_statements_enabled() and obj.adjusted_statements.exists())):
            result += ["document_type","year","series","number_format","starting_value","verification_evidence"]
        return result

    @admin.action(description=_("Attest checked external numbering history"),permissions=["change"])
    def verify_numbering_history(self,request,queryset):
        for sequence in queryset:
            try:
                sequence.attest(request.user,sequence.verification_evidence)
            except (ValidationError,PermissionDenied) as error:
                self.message_user(request,"; ".join(error.messages) if isinstance(error,ValidationError) else str(error),level=messages.ERROR)
            else:
                self.message_user(request,_("Numbering history attestation recorded."),level=messages.SUCCESS)

    def has_delete_permission(self,request,obj=None):
        return False


@admin.register(CompanyVerification)
class CompanyVerificationAdmin(admin.ModelAdmin):
    readonly_fields = tuple(field.name for field in CompanyVerification._meta.concrete_fields)
    list_display = ("id","administrator","verified_at","content_digest")

    def has_add_permission(self,request):
        return False

    def has_change_permission(self,request,obj=None):
        return False

    def has_delete_permission(self,request,obj=None):
        return False
