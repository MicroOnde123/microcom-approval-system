from django import forms
from django.utils.translation import gettext_lazy as _
from inventory.models import Succursale
from .models import Request

class ApprovalActionForm(forms.Form):
    action = forms.ChoiceField(
        label=_("Action"),
        choices=[
            ("APPROVE", _("Approve")),
            ("REJECT", _("Reject")),
            ("RETURN", _("Return for changes")),
        ]
    )
    comment = forms.CharField(
        label=_("Comment"),
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False
    )

    def __init__(self, *args, approval=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_review = bool(approval and approval.requires_stock_classification)
        if self.stock_review and (not self.is_bound or self.data.get("action") == "APPROVE"):
            self.fields["classification"] = forms.ChoiceField(
                label=_("Stock classification"), choices=[("", "---------")] + list(Request.Classification.choices),
                required=False, error_messages={"invalid_choice": _("Select Client or Microcom to approve the stock review.")})
            self.fields["succursale"] = forms.ModelChoiceField(label=_("Succursale"), required=False,
                queryset=Succursale.objects.filter(is_active=True),
                error_messages={"invalid_choice": _("Select an active succursale for a Microcom request.")})

    def clean(self):
        cleaned = super().clean()
        if not self.stock_review:
            if self.data.get("classification") or self.data.get("succursale"):
                raise forms.ValidationError(_("Only the designated stock reviewer can classify this request."))
            return cleaned
        if cleaned.get("action") == "APPROVE":
            kind = cleaned.get("classification")
            if not kind:
                self.add_error("classification", _("Select Client or Microcom to approve the stock review."))
            elif kind == Request.Classification.MICROCOM and not cleaned.get("succursale"):
                self.add_error("succursale", _("Select an active succursale for a Microcom request."))
            elif kind == Request.Classification.CLIENT and cleaned.get("succursale"):
                self.add_error("succursale", _("Client requests must not select a succursale."))
        return cleaned
