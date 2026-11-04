from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils.translation import gettext as _
from .entry_forms import NewMaterialForm, ReceiptForm, ExistingReceiptForm, CategoryForm
from .entry_services import authorize, new_token, decode_token, receive_stock, create_category, CategoryCodeConflict
from .models import Material, MaterialReceipt
from .entry_review import service_arguments, sign_review, validate_review


@login_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def material_entries(request):
    authorize(request.user)
    mode = request.POST.get("mode", request.GET.get("mode", "new"))
    mode = mode if mode in ("new", "existing") else "new"
    data = request.POST if request.method == "POST" else None
    receipt_form = (ReceiptForm if mode == "new" else ExistingReceiptForm)(data, initial={"token": new_token(request.user, mode)})
    material_form = NewMaterialForm(data if mode == "new" else None, initial={"currency": "USD"},
                                    defer_unique_validation=True)
    result = None
    review = False
    review_proof = ""
    selected_material = None
    current_stock = None
    estimated_stock = None
    if request.method == "POST":
        action = request.POST.get("action", "verify")
        try:
            valid = receipt_form.is_valid()
            if mode == "new":
                valid = material_form.is_valid() and valid
            if valid:
                arguments = service_arguments(request.user, mode, receipt_form, material_form)
                operation = decode_token(request.user, mode, arguments["token"])
                if mode == "new" and not MaterialReceipt.objects.filter(operation_token=operation).exists():
                    # A completed registration owns its code. Fresh registrations
                    # must still pass uniqueness validation before review.
                    material_form.defer_unique_validation = False
                    material_form.validate_unique()
                    valid = not material_form.errors
                if valid:
                    if action in ("confirm", "modify"):
                        validate_review(request.POST.get("review_proof"), arguments)
                    if action == "confirm":
                        receipt, _created = receive_stock(**arguments)
                        return redirect(reverse("material_entries") + "?receipt=" + str(receipt.pk) + "&mode=" + mode)
                    elif action == "verify":
                        review = True
                        review_proof = sign_review(arguments)
                    elif action != "modify":
                        raise ValidationError(_("Verify the details before confirming the receipt."))
        except ValidationError as error:
            receipt_form.add_error(None, error.messages)
        except IntegrityError:
            receipt_form.add_error(None, _("The receipt could not be saved. Check the material code and retry."))
    if mode == "existing":
        material_id = receipt_form["material"].value()
        if material_id and str(material_id).isdigit():
            selected_material = Material.objects.filter(pk=material_id).first()
        if selected_material:
            current_stock = selected_material.stock_quantity
            quantity = getattr(receipt_form, "cleaned_data", {}).get("quantity")
            if quantity is not None:
                estimated_stock = current_stock + quantity
    receipt_id = request.GET.get("receipt", "")
    if receipt_id.isdigit():
        result = MaterialReceipt.objects.filter(pk=receipt_id, created_by=request.user).prefetch_related("lines__material").first()
    return render(request, "inventory/material_entries.html", {
        "category_form": CategoryForm(prefix="category"), "mode": mode,
        "receipt_form": receipt_form, "material_form": material_form, "result": result,
        "review": review, "review_proof": review_proof,
        "selected_material": selected_material, "current_stock": current_stock, "estimated_stock": estimated_stock,
        "stock_options": list(Material.objects.values("id", "stock_quantity", "unit")) if mode == "existing" and not review else [],
    })


@login_required
@require_POST
@csrf_protect
def create_material_category(request):
    authorize(request.user)
    try:
        category, created = create_category(user=request.user, data={
            field: request.POST.get("category-" + field, "")
            for field in ("name", "code", "description")})
    except ValidationError as error:
        return JsonResponse({"errors": error.message_dict},
                            status=409 if isinstance(error, CategoryCodeConflict) else 400)
    return JsonResponse({"category": {"id": category.pk, "name": category.name, "code": category.code},
                         "created": created}, status=201 if created else 200)
