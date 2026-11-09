"""Validated filters shared by invoice listing and server-selected printing."""
from django import forms
from inventory.entry_dates import EntryDateField
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class InvoiceFilterForm(forms.Form):
    q = forms.CharField(label=_("Search"), required=False, max_length=200,
        widget=forms.TextInput(attrs={"placeholder": _("Invoice number, request reference, succursale...")}))
    date_from = EntryDateField(label=_("Date From"), required=False,
        error_messages={"invalid": _("Enter a valid issue date."),
                        "required": _("Enter both issue dates before printing filtered invoices.")})
    date_to = EntryDateField(label=_("Date To"), required=False,
        error_messages={"invalid": _("Enter a valid issue date."),
                        "required": _("Enter both issue dates before printing filtered invoices.")})
    status = forms.ChoiceField(label=_("Status"), required=False,
        choices=[("", _("All")), ("DRAFT", _("Draft")), ("FINALIZED", _("Finalized"))],
        error_messages={"invalid_choice": _("Select a valid invoice status.")})

    def __init__(self, *args, require_dates=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_from"].required = require_dates
        self.fields["date_to"].required = require_dates

    def clean(self):
        values = super().clean()
        start, end = values.get("date_from"), values.get("date_to")
        if start and end and start > end:
            self.add_error("date_to", _("The From date must not be after the To date."))
        return values


def apply_invoice_filters(queryset, filters):
    """Narrow an already authorized queryset. Never builds an unrestricted one."""
    query = filters.get("q", "")
    if query:
        # Issued documents search their frozen references/branch labels. Drafts
        # have no branch snapshot yet, so search their linked branch instead.
        queryset = queryset.filter(
            Q(number__icontains=query) | Q(request_reference_snapshot__icontains=query)
            | Q(request__request_number__icontains=query)
            | Q(succursale_snapshot__code__icontains=query)
            | Q(succursale_snapshot__name__icontains=query)
            | (Q(status="DRAFT") & (Q(succursale__code__icontains=query) | Q(succursale__name__icontains=query))))
    if filters.get("date_from"):
        queryset = queryset.filter(issue_date__gte=filters["date_from"])
    if filters.get("date_to"):
        queryset = queryset.filter(issue_date__lte=filters["date_to"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    return queryset


class InvoiceCandidateFilterForm(forms.Form):
    candidate_q = forms.CharField(label=_("Find a request for invoice creation"), required=False,
        max_length=200, widget=forms.TextInput(attrs={"type": "search"}))
