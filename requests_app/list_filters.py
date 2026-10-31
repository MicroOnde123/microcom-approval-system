"""Validated filters for already-authorized request lists."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from accounts.models import Department
from .models import Request, RequestType, RequestApproval
from .stock_report_export import ExportFilterForm


class PendingFilterForm(ExportFilterForm):
    request_type = forms.ModelChoiceField(required=False, queryset=RequestType.objects.all())


def validation_messages(form):
    labels = {'q': _("Search"), 'department': _("Request For Department"),
              'request_type': _("Request Type"), 'date_from': _("Date From"), 'date_to': _("Date To")}
    return [str(labels.get(name, _("Filters"))) + ': ' + str(message)
            for name, errors in form.errors.items() for message in errors]


class RequestListFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=200, label=_("Search"),
                        widget=forms.TextInput(attrs={'placeholder': _("Search by request reference or title...")}))
    department = forms.ModelChoiceField(required=False, queryset=Department.objects.order_by('name'),
                                        label=_("Request For Department"), empty_label=_("All Departments"))
    request_type = forms.ModelChoiceField(required=False, queryset=RequestType.objects.order_by('name'),
                                          label=_("Request Type"), empty_label=_("All Types"))
    status = forms.ChoiceField(required=False, label=_("Request Status"),
                              choices=[('', _("All Statuses"))] + [(v, _(label)) for v, label in Request.STATUS_CHOICES])
    date_from = forms.DateField(required=False, label=_("Date From"), input_formats=['%Y-%m-%d'],
                                widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, label=_("Date To"), input_formats=['%Y-%m-%d'],
                              widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))

    def clean(self):
        values = super().clean()
        start, end = values.get('date_from'), values.get('date_to')
        if start and end and start > end:
            raise forms.ValidationError(_("The start date must not be after the end date."))
        if end and end.year == 9999:
            self.add_error('date_to', _("Enter an end date before the year 9999."))
        return values


class ApprovalHistoryFilterForm(RequestListFilterForm):
    action = forms.ChoiceField(required=False, label=_("Your Action"),
                              choices=[('', _("All Actions"))] + [(v, _(label)) for v, label in RequestApproval.STEP_STATUS_CHOICES if v != 'PENDING'])


def apply_filters(rows, form, *, prefix='', date_field='submitted_at'):
    if not form.is_valid():
        return rows.none()
    values = form.cleaned_data
    if values['q']:
        rows = rows.filter(Q(**{prefix+'request_number__icontains': values['q']}) |
                           Q(**{prefix+'description__icontains': values['q']}))
    for field, lookup in [('department', 'request_for_department'), ('request_type', 'request_type'), ('status', 'status')]:
        if values[field]:
            rows = rows.filter(**{prefix+lookup: values[field]})
    zone = ZoneInfo('Africa/Kinshasa')
    if values['date_from']:
        rows = rows.filter(**{date_field+'__gte': datetime.combine(values['date_from'], time.min, tzinfo=zone)})
    if values['date_to']:
        rows = rows.filter(**{date_field+'__lt': datetime.combine(values['date_to']+timedelta(days=1), time.min, tzinfo=zone)})
    if values.get('action'):
        rows = rows.filter(status=values['action'])
    return rows
