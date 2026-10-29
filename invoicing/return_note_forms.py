"""Selection and opaque confirmation forms; no valuation input fields."""
from django import forms
from django.utils.translation import gettext_lazy as _


class ReturnNoteSelectionForm(forms.Form):
    movements = forms.MultipleChoiceField(label=_("Returned materials"),
        widget=forms.CheckboxSelectMultiple, error_messages={"required": _("Select at least one eligible complete RETURN movement.")})
    reason = forms.CharField(label=_("Operation reason"), max_length=2000,
                            widget=forms.Textarea(attrs={"rows": 3}))
    series = forms.ChoiceField(label=_("Return note series"))

    def __init__(self, *args, rows, sequences, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["movements"].choices = [(str(row["return_movement_id"]), str(row["return_movement_id"]))
                                           for row in rows if row["eligible"]]
        self.fields["series"].choices = [(row.series, row.series) for row in sequences]

    def clean_movements(self):
        values = self.cleaned_data["movements"]
        if len(values) != len(set(values)):
            raise forms.ValidationError(_("Select distinct complete stock RETURN movements."))
        return [int(value) for value in values]


class ReturnNoteConfirmationForm(forms.Form):
    handle = forms.RegexField(regex=r"\A[0-9a-f]{32}\Z", max_length=32, widget=forms.HiddenInput)
    confirm = forms.BooleanField(label=_("I confirm this returned-material valuation. Issuance is permanent."))
