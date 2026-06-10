from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Request, RequestMaterialItem
from inventory.models import Material


class RequestForm(forms.ModelForm):
    permission_group = forms.ChoiceField(
        required=False,
        label=_("Permission Group"),
        choices=[
            ("", "---------"),
            ("LEAVE_PERMISSION", _("Leave Permission")),
            ("SITE_AUTHORIZATION", _("Site Authorization")),
        ],
    )

    permission_subgroup = forms.ChoiceField(
        required=False,
        label=_("Permission Type"),
        choices=[
            ("", "---------"),
            ("BY_FOOT", _("By Foot")),
            ("BY_CAR", _("By Car")),
        ],
    )

    destination = forms.CharField(required=False, label=_("Destination"))
    exit_reason = forms.CharField(
        required=False,
        label=_("Reason / Motif"),
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    departure_time = forms.TimeField(
        required=False,
        label=_("Departure Time"),
        widget=forms.TimeInput(attrs={"type": "time"}),
    )

    return_time = forms.TimeField(
        required=False,
        label=_("Return Time"),
        widget=forms.TimeInput(attrs={"type": "time"}),
    )

    arrival_time = forms.TimeField(
        required=False,
        label=_("Arrival Time"),
        widget=forms.TimeInput(attrs={"type": "time"}),
    )

    driver_name = forms.CharField(required=False, label=_("Driver Name"))

    site = forms.CharField(required=False, label=_("Site"))
    valid_from = forms.DateField(
        required=False,
        label=_("Valid From"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    valid_to = forms.DateField(
        required=False,
        label=_("Valid To"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    microcom_agents = forms.CharField(required=False, label=_("Microcom Agents"))
    tt = forms.CharField(required=False, label=_("TT"))
    external_persons = forms.CharField(required=False, label=_("External Persons"))

    class Meta:
        model = Request
        fields = [
            "request_type",
            "description",
            "amount",
            "date_needed",
        ]
        widgets = {
            "date_needed": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "description": _("Explain why this request is needed."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["date_needed"].initial = timezone.localdate()

        # Needed because General Permission hides the normal description box.
        self.fields["description"].required = False

        metadata = getattr(self.instance, "metadata_json", None) or {}

        for field_name in [
            "permission_group",
            "permission_subgroup",
            "destination",
            "exit_reason",
            "departure_time",
            "return_time",
            "arrival_time",
            "driver_name",
            "site",
            "valid_from",
            "valid_to",
            "microcom_agents",
            "tt",
            "external_persons",
        ]:
            if field_name in metadata:
                self.fields[field_name].initial = metadata.get(field_name)

    def clean(self):
        cleaned_data = super().clean()
        request_type = cleaned_data.get("request_type")
        amount = cleaned_data.get("amount")

        if not request_type:
            return cleaned_data

        if request_type.requires_amount and not amount:
            self.add_error("amount", _("Amount is required for this type of request."))

        if request_type.is_permission_request:
            permission_group = cleaned_data.get("permission_group")
            permission_subgroup = cleaned_data.get("permission_subgroup")
            exit_reason = cleaned_data.get("exit_reason")

            if exit_reason:
                cleaned_data["description"] = exit_reason

            if not permission_group:
                self.add_error("permission_group", _("Permission group is required."))

            if permission_group == "LEAVE_PERMISSION":
                if not permission_subgroup:
                    self.add_error("permission_subgroup", _("Permission type is required."))

                required_fields = ["destination", "exit_reason", "departure_time"]

                if permission_subgroup == "BY_FOOT":
                    required_fields.append("return_time")

                if permission_subgroup == "BY_CAR":
                    required_fields.extend(["arrival_time", "driver_name"])

                for field in required_fields:
                    if not cleaned_data.get(field):
                        self.add_error(field, _("This field is required."))

            if permission_group == "SITE_AUTHORIZATION":
                required_fields = [
                    "site",
                    "valid_from",
                    "valid_to",
                    "microcom_agents",
                    "exit_reason",
                ]

                for field in required_fields:
                    if not cleaned_data.get(field):
                        self.add_error(field, _("This field is required."))

        else:
            if not cleaned_data.get("description"):
                self.add_error("description", _("Description is required."))

        return cleaned_data


class RequestMaterialItemForm(forms.ModelForm):
    material = forms.ModelChoiceField(
        queryset=Material.objects.filter(is_active=True).select_related("category"),
        required=True,
        label=_("Material"),
    )

    class Meta:
        model = RequestMaterialItem
        fields = ["material", "quantity", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["material"].queryset = (
            Material.objects.filter(is_active=True)
            .select_related("category")
            .order_by("category__name", "name")
        )

    def clean(self):
        cleaned_data = super().clean()

        material = cleaned_data.get("material")
        quantity = cleaned_data.get("quantity")

        if material and quantity:
            if quantity > material.stock_quantity:
                raise forms.ValidationError(
                    _("Only %(quantity)s %(unit)s available in stock.")
                    % {"quantity": material.stock_quantity, "unit": material.unit}
                )

        return cleaned_data


RequestMaterialItemFormSet = inlineformset_factory(
    parent_model=Request,
    model=RequestMaterialItem,
    form=RequestMaterialItemForm,
    extra=1,
    can_delete=True,
)
