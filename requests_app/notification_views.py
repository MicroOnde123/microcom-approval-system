"""Authenticated, owner-scoped notification state and bounded live presentation."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST
from django.db.models import Q
from .models import WorkflowNotification
from .notifications import counts, inbox_rows, presentation


def active(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied


def may_view_request(user, source):
    # Match request_detail's current and historical participant rules.
    if user.is_superuser or source.submitted_by_id == user.pk:
        return True
    if source.approvals.filter(Q(approver_user=user)|Q(alternate_approver_user=user)).exists():
        return True
    if user.can_manage_stock and source.material_items.exists():
        return True
    from .approval_attempts import historical_participant
    return historical_participant(source,user)


@login_required
@require_GET
@never_cache
def inbox(request):
    active(request.user)
    unread = request.GET.get("filter") == "unread"
    page = Paginator(inbox_rows(request.user,unread=unread),25).get_page(request.GET.get("page"))
    return render(request,"requests_app/notifications.html",{"notification_page":page,
        "notification_rows":[presentation(n) for n in page],"unread_only":unread})


@login_required
@require_GET
@never_cache
def snapshot(request):
    active(request.user)
    data = counts(request.user)
    unread = request.GET.get("filter") == "unread"
    approval_id = request.GET.get("approval", "")
    if approval_id.isdigit() and len(approval_id) <= 18:
        from .notifications import actionable_approvals
        data["approval_active"] = actionable_approvals(request.user).filter(pk=int(approval_id)).exists()
    recent = [presentation(n) for n in inbox_rows(request.user,unread=unread)[:10]]
    data["states"] = [{"id":row["notice"].pk,"state":row["state"]} for row in recent]
    data["html"] = render_to_string("requests_app/partials/notification_items.html",
        {"notification_rows":recent,
         "csrf_token":get_token(request)})
    return JsonResponse(data)


@login_required
@require_POST
@csrf_protect
@never_cache
def read(request, notice_id):
    active(request.user)
    notice = get_object_or_404(WorkflowNotification.objects.select_related("request"),pk=notice_id,recipient=request.user)
    view = request.POST.get("action") == "view"
    if view and not may_view_request(request.user,notice.request):
        raise PermissionDenied
    WorkflowNotification.objects.filter(pk=notice.pk,recipient=request.user,read_at__isnull=True).update(read_at=timezone.now())
    if view:
        return redirect("request_detail",request_id=notice.request_id)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"read":True})
    return redirect("notification_inbox")
