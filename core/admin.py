from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext_lazy as _
from .models import CompanyDocumentSettings, Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    search_fields = ("name",)
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CompanyDocumentSettings)
class CompanyDocumentSettingsAdmin(admin.ModelAdmin):
    readonly_fields = ("updated_at",)
    actions = ("verify_company_information",)

    @admin.action(description=_("Attest current company information"),permissions=["change"])
    def verify_company_information(self,request,queryset):
        from invoicing.models import CompanyVerification
        for configuration in queryset:
            try:
                CompanyVerification.attest(configuration,request.user)
            except (ValidationError,PermissionDenied) as error:
                self.message_user(request,"; ".join(error.messages) if isinstance(error,ValidationError) else str(error),level=messages.ERROR)
            else:
                self.message_user(request,_("Company information attestation recorded."),level=messages.SUCCESS)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not CompanyDocumentSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
