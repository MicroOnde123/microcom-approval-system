from django.db import models
from django.utils.translation import gettext_lazy as _
from .document_config import Currency, validate_logo_reference, validate_number_format
from invoicing.configuration import validate_business_timezone


class CompanyDocumentSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    company_name = models.CharField(_("Company name"), max_length=200, blank=True)
    company_address = models.TextField(_("Verified company address"), blank=True)
    contact_details = models.TextField(_("Contact details"), blank=True)
    logo_reference = models.CharField(
        _("Company logo reference"), max_length=200, blank=True,
        default="images/microcom_logo.png", validators=[validate_logo_reference],
        help_text=_("Relative path to an existing static image. No external image is fetched."))
    default_currency = models.CharField(_("Default document currency"), max_length=3, choices=Currency.choices, default=Currency.USD,
                                        error_messages={"invalid_choice": _("Select a supported currency: USD, CDF or EUR.")})
    invoice_number_format = models.CharField(
        _("Invoice number format"), max_length=100, default="FAC/{number:04d}/{year}", validators=[validate_number_format],
        help_text=_("Use {number} and optionally {year}. This preference does not allocate document numbers."))
    document_number_format = models.CharField(
        _("Other document number format"), max_length=100, blank=True, validators=[validate_number_format],
        help_text=_("Optional numbering preference for future stock documents. No numbers are allocated."))
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)
    business_timezone = models.CharField(_("Business timezone"), max_length=64,
        default="Africa/Kinshasa", validators=[validate_business_timezone])

    class Meta:
        verbose_name = _("Company and document settings")
        verbose_name_plural = _("Company and document settings")
        constraints = [models.CheckConstraint(condition=models.Q(pk=1), name="core_single_company_document_settings")]

    def __str__(self):
        return str(_("Company and document settings"))
