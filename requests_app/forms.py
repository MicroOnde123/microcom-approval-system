from django import forms
from decimal import Decimal
from django.forms import inlineformset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Request, RequestMaterialItem
from .resubmission import is_general_permission
from inventory.models import Material
from accounts.models import Department


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
    site_selections = forms.JSONField(required=False, widget=forms.HiddenInput)
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
    agent_selections = forms.JSONField(required=False, widget=forms.HiddenInput)
    tt = forms.CharField(required=False, label=_("TT"))
    external_persons = forms.CharField(required=False, label=_("External Persons"))

    class Meta:
        model = Request
        fields = [
            "request_type",
            "request_for_department",
            "description",
            "amount",
            "date_needed",
        ]
        widgets = {
            "date_needed": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "description": _("Explain why this request is needed."),
            "request_for_department": _(
                "By default, this request is assigned to your department. "
                "If you are submitting on behalf of another department, select "
                "the correct department before submitting."
            ),
        }

    def __init__(self, *args, user=None, draft=False, independent_permission_description=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.draft = draft
        self.permission_description_type_id = self.instance.request_type_id if independent_permission_description else None
        department_field = self.fields["request_for_department"]
        department_field.label = _("Request For Department")
        department_field.queryset = Department.objects.order_by("name")

        if user and not self.instance.pk:
            department_field.initial = user.department

        self.fields["date_needed"].initial = timezone.localdate()

        # Needed because General Permission hides the normal description box.
        self.fields["description"].required = False
        self.general_permission = bool(self.instance.pk and is_general_permission(self.instance))
        if self.general_permission:
            self.fields["description"].label = _("Description")
            if self.instance.status == "RETURNED":
                self.permission_description_type_id = self.instance.request_type_id

        metadata = getattr(self.instance, "metadata_json", None) or {}
        self.fields["site_selections"].initial = metadata.get("site_selections", [])
        self.site_legacy_text = metadata.get("site", "") if "site_selections" not in metadata else ""
        if self.is_bound and self.data.get("site_selections"):
            self.site_legacy_text = ""
        self.fields["agent_selections"].initial = metadata.get("agent_selections", [])
        self.agent_legacy_text = metadata.get("microcom_agents", "") if "agent_selections" not in metadata else ""
        if self.is_bound and self.data.get("agent_selections"):
            self.agent_legacy_text = ""

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

        if self.general_permission and self.instance.status != "DRAFT":
            # Django's disabled Field ignores submitted data during cleaning.
            # Set form initial too, so callers cannot substitute another value.
            self.fields["exit_reason"].disabled = True
            self.initial["exit_reason"] = metadata.get("exit_reason")
            self.fields["exit_reason"].help_text = _("The original authorization justification cannot be changed after submission.")

    def clean(self):
        cleaned_data = super().clean()
        request_type = cleaned_data.get("request_type")
        amount = cleaned_data.get("amount")

        if not request_type:
            return cleaned_data

        independent_description = (request_type.pk == self.permission_description_type_id
                                   and not request_type.requires_materials)
        if independent_description and "description" not in self.data:
            cleaned_data["description"] = self.instance.description

        if request_type.is_permission_request and cleaned_data.get("permission_group") == "SITE_AUTHORIZATION":
            from .site_selection import validate_sites
            supplied_sites = self.data.get("site_selections", "")
            if supplied_sites and "site_selections" not in self.errors:
                try:
                    sites = validate_sites(cleaned_data.get("site_selections"))
                    cleaned_data["site_selections"] = sites
                    cleaned_data["site"] = "; ".join(row["name"] for row in sites)
                    if not self.draft and not sites:
                        self.add_error("site_selections", _("Select at least one site."))
                except forms.ValidationError as exc:
                    self.add_error("site_selections", exc)
            elif not supplied_sites:
                metadata = self.instance.metadata_json or {}
                cleaned_data["site"] = metadata.get("site", "") if "site_selections" not in metadata else ""
                if not self.draft and not cleaned_data["site"]:
                    self.add_error("site_selections", _("Select at least one site."))
            from .agents import validate_people
            supplied = self.data.get("agent_selections", "")
            if supplied and "agent_selections" not in self.errors:
                try:
                    people = validate_people(cleaned_data.get("agent_selections"))
                    cleaned_data["agent_selections"] = people
                    cleaned_data["microcom_agents"] = "; ".join(p["full_name"] for p in people)
                    if not self.draft and not people:
                        self.add_error("agent_selections", _("Select at least one person."))
                except forms.ValidationError as exc:
                    self.add_error("agent_selections", exc)
            elif not supplied:
                # Only existing, unchanged legacy text may bypass structured input.
                metadata = self.instance.metadata_json or {}
                legacy = metadata.get("microcom_agents", "") if "agent_selections" not in metadata else ""
                cleaned_data["microcom_agents"] = legacy
                if not self.draft and not legacy:
                    self.add_error("agent_selections", _("Select at least one person."))

        if self.draft:
            return cleaned_data

        if request_type.requires_amount and not amount:
            self.add_error("amount", _("Amount is required for this type of request."))

        if request_type.is_permission_request:
            permission_group = cleaned_data.get("permission_group")
            permission_subgroup = cleaned_data.get("permission_subgroup")
            exit_reason = cleaned_data.get("exit_reason")

            if exit_reason and not independent_description:
                cleaned_data["description"] = exit_reason

            if not permission_group:
                self.add_error("permission_group", _("Permission group is required."))

            if permission_group == "LEAVE_PERMISSION":
                if not permission_subgroup:
                    self.add_error("permission_subgroup", _("Permission type is required."))

                # Departure and return times are optional for leave permissions.
                required_fields = ["destination", "exit_reason"]

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


class MaterialIssueNoteForm(forms.ModelForm):
    class Meta:
        model = Request
        fields = ["material_issue_note"]
        labels = {
            "material_issue_note": _("Material Issue Note"),
        }
        widgets = {
            "material_issue_note": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": _(
                        "Serial numbers, delivery remarks, installation notes, or other material issue details."
                    ),
                }
            ),
        }


class RequestMaterialItemForm(forms.ModelForm):
    quantity = forms.DecimalField(
        label=_("Quantity"), min_value=Decimal("0.01"), max_digits=10, decimal_places=2,
        error_messages={
            "min_value": _("Quantity must be greater than zero."),
            "max_decimal_places": _("Use at most two decimal places for the quantity."),
            "max_digits": _("The quantity is too large."),
            "max_whole_digits": _("The quantity is too large."),
            "invalid": _("Enter a valid quantity."),
        },
    )

    material = forms.ModelChoiceField(
        queryset=Material.objects.filter(is_active=True).select_related("category"),
        required=True,
        label=_("Material"),
    )

    class Meta:
        model = RequestMaterialItem
        fields = ["material", "quantity", "note"]

    def __init__(self, *args, draft=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.draft = draft
        if draft:
            # Drafts may retain incomplete rows, but supplied values must be valid.
            self.fields["material"].required = False
            self.fields["quantity"].required = False

        self.fields["material"].queryset = (
            Material.objects.filter(is_active=True)
            .select_related("category")
            .order_by("category__name", "name")
        )

    def clean(self):
        cleaned_data = super().clean()

        material = cleaned_data.get("material")
        quantity = cleaned_data.get("quantity")

        if material and quantity and not self.draft:
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
