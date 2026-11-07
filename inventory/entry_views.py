
"""Material registration, stock receipts, and persistent draft handling."""

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from .entry_drafts import (
    complete_draft,
    create_draft,
    get_draft,
    list_drafts,
    update_draft,
    cancel_draft,
)
from .entry_dates import canonical_date
from .entry_forms import (
    CategoryForm,
    ExistingReceiptForm,
    NewMaterialForm,
    ReceiptForm,
)
from .entry_review import (
    service_arguments,
    sign_review,
    validate_review,
)
from .entry_services import (
    CategoryCodeConflict,
    authorize,
    create_category,
    decode_token,
    new_token,
    receive_stock,
)
from .models import Material, MaterialReceipt, MaterialEntryDraft
from .pricing import authorize_price, can_change_price
from .price_views import PriceForm
from .receipt_history import receipt_queryset, display_receipt


DRAFT_RECEIPT_FIELDS = (
    "quantity",
    "received_on",
    "supplier",
    "delivery_reference",
    "notes",
)

DRAFT_MATERIAL_FIELDS = (
    "name",
    "code",
    "category",
    "description",
    "unit",
    "minimum_stock_level",
    "unit_price",
    "currency",
    "is_active",
)


def collect_draft_data(post, mode):
    """Collect permitted form values without requiring completeness."""

    values = {
        field: post.get(field, "")
        for field in DRAFT_RECEIPT_FIELDS
    }
    values["received_on"] = canonical_date(values["received_on"])

    if mode == "new":
        values["material"] = {
            field: post.get(field, "")
            for field in DRAFT_MATERIAL_FIELDS
            if field != "is_active"
        }

        values["material"]["is_active"] = (
            post.get("is_active") in ("on", "true", "True", "1")
        )

    else:
        values["material_id"] = post.get("material", "")

    return values


def draft_initial(draft):
    """Restore saved values without triggering form validation."""

    if draft is None:
        return {}

    saved = draft.data

    values = {
        field: saved.get(field, "")
        for field in DRAFT_RECEIPT_FIELDS
    }

    if draft.mode == "new":
        values.update(saved.get("material", {}))
    else:
        values["material"] = saved.get("material_id", "")

    return values


def draft_version(post):
    """Validate the submitted draft version."""

    try:
        value = int(post.get("version", ""))
    except (TypeError, ValueError):
        raise ValidationError(_("Invalid draft version."))

    if value < 1:
        raise ValidationError(_("Invalid draft version."))

    return value


def draft_url(draft):
    """Build the URL used to resume a saved draft."""

    return reverse("material_entries") + "?" + urlencode({
        "mode": draft.mode,
        "draft": draft.pk,
    })


def draft_label(draft, material_names):
    data = draft.data if isinstance(draft.data, dict) else {}
    if draft.mode == "new":
        material = data.get("material", {})
        name = material.get("name", "") if isinstance(material, dict) else ""
        return name.strip() if isinstance(name, str) and name.strip() else _("Unnamed material")
    key = str(data.get("material_id", ""))
    material = material_names.get(int(key)) if key.isdigit() and len(key) <= 18 else None
    name = material["label"] if material else _("Unnamed material")
    raw_quantity = data.get("quantity")
    quantity = str(raw_quantity).strip() if raw_quantity is not None else ""
    if not quantity:
        return _("%(material)s — quantity not entered") % {"material": name}
    unit = material["unit"] if material else ""
    return f"{name} — {quantity} {unit}".strip()


@login_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def material_entries(request):
    stock_access = request.user.is_active and (request.user.is_superuser or request.user.can_manage_stock)
    if not stock_access:
        authorize_price(request.user)
        # Pricing permission alone grants no receipt, draft or history access.
        if request.method != "GET" or request.GET.get("draft") or request.GET.get("saved_draft") or request.GET.get("receipt") or request.GET.get("mode", "existing") != "existing":
            authorize(request.user)

    mode = request.POST.get(
        "mode",
        request.GET.get("mode", "new" if stock_access else "existing"),
    )

    mode = mode if mode in ("new", "existing") else "new"

    action = (
        request.POST.get("action", "verify")
        if request.method == "POST"
        else None
    )

    # POST requests must identify drafts through submitted form data.
    # A query-string draft ID is accepted only for GET requests.
    draft_id = (
        request.POST.get("draft_id")
        if request.method == "POST"
        else request.GET.get("draft")
    )

    try:
        draft = (
            get_draft(user=request.user, draft_id=draft_id,
                      allow_completed=request.method == "POST" and action == "confirm")
            if draft_id
            else None
        )
    except (ValidationError, ValueError, TypeError):
        raise Http404(_("Draft not found."))

    if draft is not None:
        mode = draft.mode
    submitted_version = (request.POST.get("version", "") if request.method == "POST"
                         else draft.version) if draft else None

    posted = (
        request.POST
        if request.method == "POST"
        else None
    )

    initial = (
        draft_initial(draft)
        if request.method == "GET"
        else {}
    )

    receipt_form = (
        ReceiptForm if mode == "new" else ExistingReceiptForm
    )(
        posted,
        initial={
            **initial,
            "token": (
                draft.signed_token
                if draft
                else new_token(request.user, mode)
            ),
        },
    )

    material_form = NewMaterialForm(
        posted if mode == "new" else None,
        initial={
            "currency": "USD",
            **initial,
        },
        defer_unique_validation=True,
    )

    result = None
    review = False
    review_proof = ""

    selected_material = None
    current_stock = None
    estimated_stock = None

    if posted is not None:

        # ---------------------------------------------
        # SAVE DRAFT
        # ---------------------------------------------

        if action == "save_draft":

            token = posted.get("token", "")
            values = collect_draft_data(posted, mode)

            try:
                if draft is not None:

                    if token != draft.signed_token:
                        raise ValidationError(
                            _("Invalid draft receipt token.")
                        )

                    draft = update_draft(
                        user=request.user,
                        draft_id=draft.pk,
                        version=draft_version(posted),
                        data=values,
                    )

                else:
                    draft = create_draft(
                        user=request.user,
                        mode=mode,
                        token=token,
                        data=values,
                    )

            except (ValidationError, IntegrityError) as error:

                message = (
                    error.messages
                    if isinstance(error, ValidationError)
                    else [
                        _(
                            "The draft could not be saved. "
                            "Reload the page and retry."
                        )
                    ]
                )

                # Restore incomplete values without displaying
                # unrelated required-field validation errors.
                initial_values = {
                    **values,
                    **(
                        values.get("material", {})
                        if mode == "new"
                        else {
                            "material": values.get(
                                "material_id", ""
                            )
                        }
                    ),
                }

                receipt_form = (
                    ReceiptForm
                    if mode == "new"
                    else ExistingReceiptForm
                )(
                    initial={
                        **initial_values,
                        "token": token,
                    }
                )

                material_form = NewMaterialForm(
                    initial={
                        "currency": "USD",
                        **initial_values,
                    },
                    defer_unique_validation=True,
                )

                receipt_form.cleaned_data = {}
                receipt_form.add_error(None, message)

            else:
                # Only identifiers travel in the redirect. The notification's
                # name and resume link are resolved through ownership checks.
                return redirect(reverse("material_entries") + "?" + urlencode({
                    "mode": mode, "saved_draft": draft.pk,
                }))

        # ---------------------------------------------
        # VERIFY / MODIFY / CONFIRM
        # ---------------------------------------------

        else:

            try:
                if draft is not None:

                    version = draft_version(posted)

                    retry = action == "confirm" and draft.status == MaterialEntryDraft.Status.COMPLETED
                    if draft.version != version + (1 if retry else 0):
                        raise ValidationError(
                            _(
                                "This draft has changed. "
                                "Reload it before continuing."
                            )
                        )

                    if (
                        posted.get("token", "")
                        != draft.signed_token
                    ):
                        raise ValidationError(
                            _("Invalid draft receipt token.")
                        )

                if action not in (
                    "verify",
                    "modify",
                    "confirm",
                ):
                    raise ValidationError(
                        _(
                            "Verify the details before "
                            "confirming the receipt."
                        )
                    )

                valid = receipt_form.is_valid()

                if mode == "new":
                    valid = (
                        material_form.is_valid()
                        and valid
                    )

                if valid:

                    arguments = service_arguments(
                        request.user,
                        mode,
                        receipt_form,
                        material_form,
                    )

                    operation = decode_token(
                        request.user,
                        mode,
                        arguments["token"],
                    )

                    # New registrations must pass uniqueness
                    # validation before verification.
                    if (
                        mode == "new"
                        and not MaterialReceipt.objects.filter(
                            operation_token=operation
                        ).exists()
                    ):
                        material_form.defer_unique_validation = False
                        material_form.validate_unique()

                        valid = not material_form.errors

                    if valid:

                        if action in ("modify", "confirm"):
                            validate_review(
                                posted.get("review_proof"),
                                arguments,
                                draft_context={"id": draft.pk, "version": version} if draft else None,
                            )

                        # ---------------------------------
                        # CONFIRM RECEIPT
                        # ---------------------------------

                        if action == "confirm":

                            if draft is not None:

                                receipt, _created = complete_draft(
                                    user=request.user,
                                    draft_id=draft.pk,
                                    version=version,
                                    arguments=arguments,
                                    review_proof=posted.get(
                                        "review_proof", ""
                                    ),
                                )

                            else:

                                receipt, _created = receive_stock(
                                    **arguments
                                )

                            return redirect(
                                reverse("material_entries")
                                + "?"
                                + urlencode({
                                    "receipt": receipt.pk,
                                    "mode": mode,
                                })
                            )

                        # ---------------------------------
                        # VERIFY RECEIPT
                        # ---------------------------------

                        if action == "verify":
                            review = True
                            review_proof = sign_review(
                                arguments,
                                draft_context={"id": draft.pk, "version": version} if draft else None,
                            )

            except ValidationError as error:
                receipt_form.add_error(
                    None,
                    error.messages,
                )

            except IntegrityError:
                receipt_form.add_error(
                    None,
                    _(
                        "The receipt could not be saved. "
                        "Check the material code and retry."
                    ),
                )

    # -------------------------------------------------
    # EXISTING MATERIAL STOCK ESTIMATES
    # -------------------------------------------------

    if mode == "existing":

        material_id = receipt_form["material"].value()

        if (
            material_id
            and str(material_id).isdigit() and len(str(material_id)) <= 18
        ):
            selected_material = Material.objects.filter(
                pk=material_id
            ).first()

        if selected_material:

            current_stock = selected_material.stock_quantity

            quantity = getattr(
                receipt_form,
                "cleaned_data",
                {},
            ).get("quantity")

            if quantity is None:

                raw = receipt_form["quantity"].value()

                try:
                    quantity = (
                        Decimal(str(raw))
                        if raw not in (None, "")
                        else None
                    )

                    if quantity is not None and (
                        not quantity.is_finite()
                        or quantity <= 0
                    ):
                        quantity = None

                except (
                    InvalidOperation,
                    TypeError,
                    ValueError,
                ):
                    quantity = None

            if quantity is not None:
                estimated_stock = (
                    current_stock + quantity
                )

    # -------------------------------------------------
    # RECEIPT CONFIRMATION RESULT
    # -------------------------------------------------

    receipt_id = request.GET.get("receipt", "")

    if receipt_id.isdigit():

        result = (
            receipt_queryset().filter(
                pk=receipt_id,
                created_by=request.user,
            )
            .first()
        )

    # -------------------------------------------------
    # RENDER MATERIAL ENTRIES PAGE
    # -------------------------------------------------

    drafts_page = Paginator(list_drafts(user=request.user) if stock_access else [], 10).get_page(request.GET.get("draft_page"))
    material_ids = [int(d.data.get("material_id")) for d in drafts_page
                    if d.mode == "existing" and isinstance(d.data, dict)
                    and str(d.data.get("material_id", "")).isdigit()
                    and len(str(d.data["material_id"])) <= 18]
    names = {m.pk: {"label": f"{m.name} ({m.code})", "unit": m.unit}
             for m in Material.objects.filter(pk__in=material_ids).only("id", "name", "code", "unit")}
    for saved in drafts_page:
        saved.entry_label = draft_label(saved, names)
        saved.entry_mode_label = _("Existing Material Receipt") if saved.mode == "existing" else saved.get_mode_display()

    saved_draft = None
    saved_draft_name = ""
    if request.method == "GET" and not draft and request.GET.get("saved_draft"):
        try:
            saved_draft = get_draft(user=request.user, draft_id=request.GET["saved_draft"])
        except (ValidationError, ValueError, TypeError):
            pass  # An inaccessible/stale notification never reveals draft data.
        if saved_draft:
            if saved_draft.mode == "new":
                value = saved_draft.data.get("material", {}).get("name", "")
                saved_draft_name = value if isinstance(value, str) else ""
            else:
                key = str(saved_draft.data.get("material_id", ""))
                if key.isdigit() and len(key) <= 18:
                    saved_draft_name = Material.objects.filter(pk=int(key)).values_list("name", flat=True).first() or ""

    return render(
        request,
        "inventory/material_entries.html",
        {
            "can_receive_stock": stock_access,
            "can_edit_price": can_change_price(request.user),
            "price_form": PriceForm(),
            "draft": draft,
            "draft_version": submitted_version,
            "saved_drafts": drafts_page,
            "saved_draft": saved_draft,
            "saved_draft_name": saved_draft_name,
            "saved_draft_url": draft_url(saved_draft) if saved_draft else "",

            "category_form": CategoryForm(
                prefix="category"
            ),

            "mode": mode,

            "receipt_form": receipt_form,

            "material_form": material_form,

            "result": result,
            "confirmation": display_receipt(result) if result else None,

            "review": review,

            "review_proof": review_proof,

            "selected_material": selected_material,

            "current_stock": current_stock,

            "estimated_stock": estimated_stock,

            "stock_options": (
                list(
                    Material.objects.values(
                        "id",
                        "stock_quantity",
                        "unit",
                        "unit_price",
                        "currency",
                    )
                )
                if mode == "existing" and not review
                else []
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def cancel_material_entry_draft(request, draft_id):
    """GET only reviews cancellation; an explicit, versioned POST changes state."""
    authorize(request.user)
    draft = MaterialEntryDraft.objects.filter(pk=draft_id, owner=request.user).first()
    if draft is None:
        raise Http404(_("Draft not found."))
    version = request.POST.get("version", "") if request.method == "POST" else draft.version
    error = ""
    if request.method == "POST":
        try:
            if request.POST.get("confirm_cancel") != "yes":
                raise ValidationError(_("Confirm cancellation before continuing."))
            draft, cancelled = cancel_draft(user=request.user, draft_id=draft.pk,
                                           version=draft_version(request.POST))
        except ValidationError as exc:
            error = " ".join(exc.messages)
        else:
            messages.success(request, _("Draft cancelled successfully.") if cancelled else _("This draft was already cancelled."))
            return redirect(reverse("material_entries") + "?" + urlencode({"mode": draft.mode}))
    return render(request, "inventory/cancel_entry_draft.html", {
        "draft": draft, "draft_version": version, "error": error,
    }, status=409 if error else 200)


@login_required
@require_POST
@csrf_protect
def create_material_category(request):
    """Create a material category without changing stock."""

    authorize(request.user)

    try:
        category, created = create_category(
            user=request.user,
            data={
                field: request.POST.get(
                    "category-" + field,
                    "",
                )
                for field in (
                    "name",
                    "code",
                    "description",
                )
            },
        )

    except ValidationError as error:

        return JsonResponse(
            {
                "errors": error.message_dict,
            },
            status=(
                409
                if isinstance(
                    error,
                    CategoryCodeConflict,
                )
                else 400
            ),
        )

    return JsonResponse(
        {
            "category": {
                "id": category.pk,
                "name": category.name,
                "code": category.code,
            },
            "created": created,
        },
        status=201 if created else 200,
    )
