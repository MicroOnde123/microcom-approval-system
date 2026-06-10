import csv
from django.http import HttpResponse
from urllib import request

from urllib import request

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.crypto import get_random_string
from django.contrib import messages
from django.db import models
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone

from .forms import RequestForm, RequestMaterialItemFormSet
from .approval_forms import ApprovalActionForm
from .stock_forms import ReturnToStockForm
from .models import Request, RequestApproval, RequestAttachment, RequestMaterialItem, StockMovement, RequestAuditLog
from .services import submit_request, approve_step, reject_step, return_step, resubmit_request
from django.utils.translation import gettext as _



MATERIAL_FORMSET_PREFIX = "material_items"


def requires_materials(req):
    return req.request_type and req.request_type.requires_materials


def request_type_behavior_context(form):
    request_type_field = form.fields["request_type"]
    queryset = request_type_field.queryset

    return {
        str(request_type.id): {
            "is_permission_request": request_type.is_permission_request,
            "requires_materials": request_type.requires_materials,
            "requires_amount": request_type.requires_amount,
        }
        for request_type in queryset
    }


def save_attachments(request, req):
    files = request.FILES.getlist("attachments")

    for f in files:
        RequestAttachment.objects.create(
            request=req,
            file=f,
            original_name=f.name,
            uploaded_by=request.user,
        )

def build_permission_metadata(form):
    cleaned = form.cleaned_data

    return {
        "permission_group": cleaned.get("permission_group"),
        "permission_subgroup": cleaned.get("permission_subgroup"),
        "destination": cleaned.get("destination"),
        "exit_reason": cleaned.get("exit_reason"),
        "departure_time": (
            cleaned.get("departure_time").strftime("%H:%M")
            if cleaned.get("departure_time")
            else None
        ),
        "return_time": (
            cleaned.get("return_time").strftime("%H:%M")
            if cleaned.get("return_time")
            else None
        ),
        "arrival_time": (
            cleaned.get("arrival_time").strftime("%H:%M")
            if cleaned.get("arrival_time")
            else None
        ),
        "driver_name": cleaned.get("driver_name"),
        "site": cleaned.get("site"),
        "valid_from": (
            cleaned.get("valid_from").strftime("%Y-%m-%d")
            if cleaned.get("valid_from")
            else None
        ),
        "valid_to": (
            cleaned.get("valid_to").strftime("%Y-%m-%d")
            if cleaned.get("valid_to")
            else None
        ),
        "microcom_agents": cleaned.get("microcom_agents"),
        "tt": cleaned.get("tt"),
        "external_persons": cleaned.get("external_persons"),
    }

@login_required
def create_request(request):
    if not request.user.department:
        messages.error(request, "Your account is not linked to any department.")
        return redirect("dashboard")

    if request.method == "POST":
        form = RequestForm(request.POST, request.FILES)
        formset = RequestMaterialItemFormSet(
            request.POST,
            prefix=MATERIAL_FORMSET_PREFIX,
        )

        if form.is_valid():
            req = form.save(commit=False)
            req.request_number = f"REQ-{get_random_string(6).upper()}"
            req.submitted_by = request.user
            req.department = request.user.department
            req.metadata_json = build_permission_metadata(form)

            material_request = requires_materials(req)

            if material_request:
                if not formset.is_valid():
                    return render(
                        request,
                        "requests_app/create_request.html",
                        {
                            "form": form,
                            "formset": formset,
                            "request_type_behavior": request_type_behavior_context(form),
                        },
                    )

                items = formset.save(commit=False)

                if not items:
                    messages.error(request, "At least one material is required for material requests.")
                    return render(
                        request,
                        "requests_app/create_request.html",
                        {
                            "form": form,
                            "formset": formset,
                            "request_type_behavior": request_type_behavior_context(form),
                        },
                    )

            req.save()

            if material_request:
                for item in items:
                    item.request = req
                    item.save()

                for obj in formset.deleted_objects:
                    obj.delete()

            save_attachments(request, req)

            try:
                submit_request(req)
            except Exception:
                req.delete()
                messages.error(request, "No approval workflow is configured for this request type.")
                return render(
                    request,
                    "requests_app/create_request.html",
                    {
                        "form": form,
                        "formset": formset,
                        "request_type_behavior": request_type_behavior_context(form),
                    },
                )

            messages.success(request, "Request submitted successfully.")
            return redirect("dashboard")

    else:
        form = RequestForm()
        formset = RequestMaterialItemFormSet(prefix=MATERIAL_FORMSET_PREFIX)

    return render(
        request,
        "requests_app/create_request.html",
        {
            "form": form,
            "formset": formset,
            "request_type_behavior": request_type_behavior_context(form),
        },
    )

def is_stock_manager(user):
    return (
        user.is_superuser
        or 
            getattr(user, "can_manage_stock", False)
    )
    
@login_required
def my_requests(request):
    qs = Request.objects.filter(submitted_by=request.user).order_by("-submitted_at")
    return render(request, "requests_app/my_requests.html", {"requests": qs})


@login_required
def pending_approvals(request):
    approvals = RequestApproval.objects.filter(
        models.Q(approver_user=request.user)
        | models.Q(alternate_approver_user=request.user),
        status="PENDING",
        request__current_step_order=models.F("step_order"),
    ).select_related(
        "request",
        "request__request_type",
    ).order_by("request__date_needed", "created_at")

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    request_type = request.GET.get("request_type", "").strip()
    q = request.GET.get("q", "").strip()

    if date_from:
        approvals = approvals.filter(request__date_needed__gte=date_from)

    if date_to:
        approvals = approvals.filter(request__date_needed__lte=date_to)

    if request_type:
        approvals = approvals.filter(request__request_type_id=request_type)

    if q:
        approvals = approvals.filter(
            models.Q(request__request_number__icontains=q)
            | models.Q(request__submitted_by__username__icontains=q)
            | models.Q(request__submitted_by__full_name__icontains=q)
            | models.Q(request__submitted_by__email__icontains=q)
    )

    request_types = Request.objects.values_list(
        "request_type__id",
        "request_type__name",
    ).distinct()
    today = timezone.now().date()
    
    return render(
        request,
        "requests_app/pending_approvals.html",
        {
            "approvals": approvals,
            "request_types": request_types,
            "date_from": date_from,
            "date_to": date_to,
            "selected_request_type": request_type,
            "today": today,
            "q": q,
        },
    )


@login_required
def approval_detail(request, approval_id):
    approval = get_object_or_404(
        RequestApproval.objects.select_related(
            "request",
            "request__request_type",
            "approver_user",
            "alternate_approver_user",
        ).filter(
            models.Q(approver_user=request.user)
            | models.Q(alternate_approver_user=request.user)
        ),
        id=approval_id,
    )

    if request.method != "POST" and (
        approval.status != "PENDING"
        or approval.request.current_step_order != approval.step_order
    ):
        messages.error(request, "This approval is no longer active.")
        return redirect("pending_approvals")

    if request.method == "POST":
        form = ApprovalActionForm(request.POST)

        if form.is_valid():
            action = form.cleaned_data["action"]
            comment = form.cleaned_data["comment"]

            try:
                if action == "APPROVE":
                    approve_step(approval, request.user, comment)
                    messages.success(request, "Request approved successfully.")
                elif action == "REJECT":
                    reject_step(approval, request.user, comment)
                    messages.success(request, "Request rejected successfully.")
                elif action == "RETURN":
                    return_step(approval, request.user, comment)
                    messages.success(request, "Request returned for changes.")
            except Exception as e:
                messages.error(request, str(e))
                return redirect("approval_detail", approval_id=approval.id)

            return redirect("pending_approvals")
    else:
        form = ApprovalActionForm()

    return render(
        request,
        "requests_app/approval_detail.html",
        {"approval": approval, "request_obj": approval.request, "form": form},
    )


@login_required
def request_detail(request, request_id):
    request_obj = get_object_or_404(
        Request.objects.prefetch_related(
            "approvals__approver_user",
            "attachments",
            "audit_logs",
            "material_items__material__category",
        ),
        id=request_id,
    )

    is_submitter = request_obj.submitted_by == request.user
    is_approver = request_obj.approvals.filter(
        models.Q(approver_user=request.user)
        | models.Q(alternate_approver_user=request.user)
    ).exists()
    is_stock_user = is_stock_manager(request.user) and request_obj.material_items.exists()
    
    if not is_submitter and not is_approver and not request.user.is_superuser and not is_stock_user:
        return HttpResponseForbidden("You are not allowed to view this request.")
    

    return render(request, "requests_app/request_detail.html", {"request_obj": request_obj})


@login_required
def edit_request(request, request_id):
    request_obj = get_object_or_404(Request, id=request_id, submitted_by=request.user)

    if request_obj.status != "RETURNED":
        messages.error(request, "Only returned requests can be edited.")
        return redirect("request_detail", request_id=request_obj.id)

    if request.method == "POST":
        form = RequestForm(request.POST, request.FILES, instance=request_obj)

        if form.is_valid():
            req = form.save(commit=False)
            req.department = request.user.department
            req.metadata_json = build_permission_metadata(form)

            material_request = requires_materials(req)

            formset = RequestMaterialItemFormSet(
                request.POST,
                instance=req,
                prefix=MATERIAL_FORMSET_PREFIX,
            )

            if material_request:
                if not formset.is_valid():
                    return render(
                        request,
                        "requests_app/edit_request.html",
                        {
                            "form": form,
                            "formset": formset,
                            "request_obj": request_obj,
                            "request_type_behavior": request_type_behavior_context(form),
                        },
                    )

                items = formset.save(commit=False)

                existing_items_count = req.material_items.count()
                deleted_items_count = len(formset.deleted_objects)
                remaining_existing_count = existing_items_count - deleted_items_count

                if not items and remaining_existing_count <= 0:
                    messages.error(request, "At least one material is required for material requests.")
                    return render(
                        request,
                        "requests_app/edit_request.html",
                        {
                            "form": form,
                            "formset": formset,
                            "request_obj": request_obj,
                            "request_type_behavior": request_type_behavior_context(form),
                        },
                    )
            else:
                formset = RequestMaterialItemFormSet(
                    instance=req,
                    prefix=MATERIAL_FORMSET_PREFIX,
                )

            req.save()

            if material_request:
                formset.save()
            else:
                req.material_items.all().delete()

            save_attachments(request, req)
            resubmit_request(req, request.user)

            messages.success(request, "Request updated and resubmitted successfully.")
            return redirect("request_detail", request_id=req.id)

        formset = RequestMaterialItemFormSet(
            request.POST,
            instance=request_obj,
            prefix=MATERIAL_FORMSET_PREFIX,
        )

    else:
        form = RequestForm(instance=request_obj)
        formset = RequestMaterialItemFormSet(
            instance=request_obj,
            prefix=MATERIAL_FORMSET_PREFIX,
        )

    return render(
        request,
        "requests_app/edit_request.html",
        {
            "form": form,
            "formset": formset,
            "request_obj": request_obj,
            "request_type_behavior": request_type_behavior_context(form),
        },
    )


@login_required
def approved_document(request, request_id):
    request_obj = get_object_or_404(
        Request.objects.prefetch_related(
            "material_items__material",
            "approvals__approver_user",
        ),
        id=request_id,
    )

    allowed = (
        request.user == request_obj.submitted_by
        or request_obj.approvals.filter(
            models.Q(approver_user=request.user)
            | models.Q(alternate_approver_user=request.user)
        ).exists()
        or request.user.is_superuser
        or (
            is_stock_manager(request.user)
            and request_obj.material_items.exists()
        )
    )

    if not allowed:
        return HttpResponseForbidden("You are not allowed to view this document.")

    if request_obj.status != "APPROVED":
        messages.error(request, "This request is not approved yet.")
        return redirect("request_detail", request_id=request_obj.id)

    approvals = request_obj.approvals.filter(
        status="APPROVED"
    ).order_by("step_order")

    return render(
        request,
        "requests_app/approved_document.html",
        {
            "request_obj": request_obj,
            "approvals": approvals,
        },
    )

@login_required
def permission_document(request, request_id):
    request_obj = get_object_or_404(
        Request.objects.prefetch_related(
            "approvals__approver_user",
        ),
        id=request_id,
    )

    allowed = (
        request.user == request_obj.submitted_by
        or request_obj.approvals.filter(
            models.Q(approver_user=request.user)
            | models.Q(alternate_approver_user=request.user)
        ).exists()
        or request.user.is_superuser
    )

    if not allowed:
        return HttpResponseForbidden("You are not allowed to view this document.")

    if request_obj.status != "APPROVED":
        messages.error(request, "This request is not approved yet.")
        return redirect("request_detail", request_id=request_obj.id)

    metadata = request_obj.metadata_json or {}

    if not metadata.get("permission_group"):
        messages.error(request, "This request is not a permission request.")
        return redirect("request_detail", request_id=request_obj.id)

    approvals = request_obj.approvals.filter(
        status="APPROVED"
    ).order_by("step_order")

    return render(
        request,
        "requests_app/permission_document.html",
        {
            "request_obj": request_obj,
            "metadata": metadata,
            "approvals": approvals,
        },
    )

@login_required
def approval_history(request):
    approvals = RequestApproval.objects.filter(
        models.Q(approver_user=request.user)
        | models.Q(alternate_approver_user=request.user)
    ).exclude(
        status="PENDING"
    ).select_related(
        "request",
        "request__request_type",
    ).order_by("-acted_at")

    return render(
        request,
        "requests_app/approval_history.html",
        {"approvals": approvals},
    )
@login_required
def material_reports(request):
    if not is_stock_manager(request.user):
        return HttpResponseForbidden("You are not allowed to access material reports.")

    requests = Request.objects.filter(
        status="APPROVED",
        material_items__isnull=False,
       
    ).distinct().prefetch_related(
        "material_items__material__category",
        "approvals__approver_user",
    ).select_related(
        "submitted_by",
        "department",
        "request_type",
    )

    q = request.GET.get("q", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    department = request.GET.get("department", "").strip()

    if q:
        requests = requests.filter(
            models.Q(request_number__icontains=q)
            | models.Q(submitted_by__username__icontains=q)
            | models.Q(submitted_by__full_name__icontains=q)
            | models.Q(material_items__material__name__icontains=q)
            | models.Q(material_items__material__code__icontains=q)
        )

    if date_from:
        requests = requests.filter(date_needed__gte=date_from)

    if date_to:
        requests = requests.filter(date_needed__lte=date_to)

    if department:
        requests = requests.filter(department_id=department)

    departments = Request.objects.exclude(
        department__isnull=True
    ).values_list(
        "department__id",
        "department__name",
    ).distinct()

    requests = requests.order_by("-finalized_at", "-submitted_at")

    return render(
        request,
        "requests_app/material_reports.html",
        {
            "requests": requests,
            "departments": departments,
            "q": q,
            "date_from": date_from,
            "date_to": date_to,
            "selected_department": department,
        },
    )

@login_required
def export_material_report_csv(request):
    if not is_stock_manager(request.user):
        return HttpResponseForbidden("You are not allowed to export material reports.")

    requests = Request.objects.filter(
        status="APPROVED",
        material_items__isnull=False,
    ).distinct().prefetch_related(
        "material_items__material__category",
        "approvals__approver_user",
    ).select_related(
        "submitted_by",
        "department",
        "request_type",
    )

    q = request.GET.get("q", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    department = request.GET.get("department", "").strip()

    if q:
        requests = requests.filter(
            models.Q(request_number__icontains=q)
            | models.Q(submitted_by__username__icontains=q)
            | models.Q(submitted_by__full_name__icontains=q)
            | models.Q(material_items__material__name__icontains=q)
            | models.Q(material_items__material__code__icontains=q)
        )

    if date_from:
        requests = requests.filter(date_needed__gte=date_from)

    if date_to:
        requests = requests.filter(date_needed__lte=date_to)

    if department:
        requests = requests.filter(department_id=department)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="material_report.csv"'

    writer = csv.writer(response)

    writer.writerow([
        _("Request Number"),
        _("Requester"),
        _("Department"),
        _("Date Needed"),
        _("Approved Date"),
        _("Material"),
        _("Material Code"),
        _("Category"),
        _("Quantity"),
        _("Unit"),
        _("Available Stock"),
        _("Description"),
        _("Approvers"),
    ])

    for req in requests.order_by("-finalized_at", "-submitted_at"):
        approvers = ", ".join([
            approval.approver_user.full_name or approval.approver_user.username
            for approval in req.approvals.all()
            if approval.status == "APPROVED"
        ])

        for item in req.material_items.all():
            writer.writerow([
                req.request_number,
                req.submitted_by.full_name or req.submitted_by.username,
                req.department.name if req.department else "",
                req.date_needed,
                req.finalized_at.strftime("%Y-%m-%d %H:%M") if req.finalized_at else "",
                item.material.name,
                item.material.code,
                item.material.category.name if item.material.category else "",
                item.quantity,
                item.material.unit,
                item.material.stock_quantity,
                req.description,
                approvers,
            ])

    return response
    
@login_required
def bulk_print_material_documents(request):
    if not is_stock_manager(request.user):
        return HttpResponseForbidden("You are not allowed to bulk print material documents.")

    if request.method != "POST":
        return redirect("material_reports")

    selected_ids = request.POST.getlist("selected_requests")

    if not selected_ids:
        messages.error(request, "Select at least one material request to print.")
        return redirect("material_reports")

    requests = Request.objects.filter(
        id__in=selected_ids,
        status="APPROVED",
        material_items__isnull=False,
        
    ).distinct().prefetch_related(
        "material_items__material",
        "approvals__approver_user",
    ).select_related(
        "submitted_by",
        "department",
    ).order_by("-finalized_at", "-submitted_at")

    return render(
        request,
        "requests_app/bulk_print_material_documents.html",
        {"requests": requests},
    )

@login_required
def return_material_to_stock(request, item_id):
    if not is_stock_manager(request.user):
        return HttpResponseForbidden(_("You are not allowed to return stock."))

    item = get_object_or_404(
        RequestMaterialItem.objects.select_related(
            "request",
            "material",
        ),
        id=item_id,
        request__status="APPROVED",
    )

    req = item.request
    material = item.material

    if request.method == "POST":
        form = ReturnToStockForm(request.POST)

        if form.is_valid():
            quantity = form.cleaned_data["quantity"]
            reason = form.cleaned_data["reason"]

            if quantity > item.quantity:
                messages.error(
                    request,
                    _("Returned quantity cannot be greater than requested quantity."),
                )
                return redirect("return_material_to_stock", item_id=item.id)

            material.stock_quantity += quantity
            material.save(update_fields=["stock_quantity"])

            StockMovement.objects.create(
                material=material,
                request=req,
                quantity=quantity,
                movement_type="RETURN",
                performed_by=request.user,
                note=_("Material returned to stock."),
                return_reason=reason,
            )

            RequestAuditLog.objects.create(
                request=req,
                action="STOCK_RETURNED",
                performed_by=request.user,
                comment=_("Returned %(quantity)s %(unit)s of %(material)s to stock. Reason: %(reason)s")
                % {
                    "quantity": quantity,
                    "unit": material.unit or "",
                    "material": material.name,
                    "reason": reason,
                },
            )

            messages.success(
                request,
                _("Material returned to stock successfully."),
            )

            return redirect("material_reports")

    else:
        form = ReturnToStockForm()

    return render(
        request,
        "requests_app/return_material_to_stock.html",
        {
            "form": form,
            "item": item,
            "request_obj": req,
            "material": material,
        },
    )

@login_required
def notification_count(request):
    pending_count = RequestApproval.objects.filter(
        models.Q(approver_user=request.user)
        | models.Q(alternate_approver_user=request.user),
        status="PENDING",
        request__current_step_order=models.F("step_order"),
    ).count()

    returned_count = Request.objects.filter(
        submitted_by=request.user,
        status="RETURNED",
    ).count()

    return JsonResponse({
        "pending": pending_count,
        "returned": returned_count,
    })
