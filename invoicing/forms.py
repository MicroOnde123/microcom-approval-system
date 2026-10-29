from django import forms
from django.forms import BaseFormSet, formset_factory
from django.utils.translation import gettext_lazy as _

from core.document_config import Currency


class CreateInvoiceForm(forms.Form):
    currency = forms.ChoiceField(label=_("Invoice currency"),choices=Currency.choices)


class DraftInformationForm(forms.Form):
    note = forms.CharField(label=_("Invoice note"),required=False,max_length=2000,widget=forms.Textarea(attrs={"rows":3}))
    revision = forms.CharField(widget=forms.HiddenInput)


class PriceForm(forms.Form):
    line_id = forms.IntegerField(widget=forms.HiddenInput)
    unit_price = forms.DecimalField(label=_("Unit price"),required=False,min_value=0,max_digits=16,decimal_places=4)


class PriceFormSet(BaseFormSet):
    def __init__(self,*args,lines,**kwargs):
        self.lines = list(lines)
        kwargs.setdefault("initial",[{"line_id":line.pk,"unit_price":line.unit_price} for line in self.lines])
        super().__init__(*args,**kwargs)
        for form,line in zip(self.forms,self.lines):
            form.material_description = line.description_snapshot
            form.net_quantity = line.quantity
            form.currency = line.currency

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        ids = [form.cleaned_data.get("line_id") for form in self.forms]
        if len(ids)!=len(self.lines) or set(ids)!={line.pk for line in self.lines}:
            raise forms.ValidationError(_("The submitted invoice lines are invalid. Reload the draft."))


Prices = formset_factory(PriceForm,formset=PriceFormSet,extra=0,max_num=1000,validate_max=True,absolute_max=1000)


class FinalizeInvoiceForm(forms.Form):
    series = forms.ChoiceField(label=_("Invoice series"))
    revision = forms.CharField(widget=forms.HiddenInput)
    confirm = forms.BooleanField(label=_("I confirm the prices and net quantities. Finalization is permanent."))

    def __init__(self,*args,sequences,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["series"].choices = [(row.series,row.series) for row in sequences]
