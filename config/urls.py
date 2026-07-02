from django.contrib import admin
from django.urls import path, include
from core.views import dashboard
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from accounts.forms import CustomPasswordResetForm

from requests_app.views import (
    create_request,
    my_requests,
    pending_approvals,
    approval_detail,
    request_detail,
    update_material_issue_note,
    edit_request,
    approved_document,
    approval_history,
    permission_document,
    material_reports,
    bulk_print_material_documents,
    export_material_report_csv,
    notification_count, return_material_to_stock, export_material_report_excel,
)

urlpatterns = [
    # LANGUAGE SWITCHER
    path("i18n/", include("django.conf.urls.i18n")),

    # DASHBOARD
    path("", dashboard, name="dashboard"),

    # ADMIN
    path("admin/", admin.site.urls),

    # AUTH
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # REQUESTS
    path("requests/", my_requests, name="my_requests"),
    path("requests/create/", create_request, name="create_request"),
    path("requests/<int:request_id>/", request_detail, name="request_detail"),
    path(
        "requests/<int:request_id>/material-issue-note/",
        update_material_issue_note,
        name="update_material_issue_note",
    ),
    path("requests/<int:request_id>/edit/", edit_request, name="edit_request"),
    

    # APPROVALS
    path("approvals/pending/", pending_approvals, name="pending_approvals"),
    path("approvals/<int:approval_id>/", approval_detail, name="approval_detail"),
    path("approvals/history/", approval_history, name="approval_history"),

    # DOCUMENTS
    path(
        "requests/<int:request_id>/approved-document/",
        approved_document,
        name="approved_document",
    ),

    path(
        "requests/<int:request_id>/permission-document/",
        permission_document,
        name="permission_document",
    ),

    # MATERIAL REPORTS
    path(
        "materials/reports/",
        material_reports,
        name="material_reports",
    ),

    path(
        "materials/reports/bulk-print/",
        bulk_print_material_documents,
        name="bulk_print_material_documents",
    ),

    path(
        "materials/reports/export-csv/",
        export_material_report_csv,
        name="export_material_report_csv",
    ),

    path(
        "notifications/count/",
        notification_count,
        name="notification_count",
    ),
    path(
        "materials/return/<int:item_id>/",
        return_material_to_stock,
        name="return_material_to_stock",
    ),
    path(
        "materials/reports/export-excel/",
        export_material_report_excel,
        name="export_material_report_excel",
    ),

    # PASSWORD RESET
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="auth/password_reset.html",
            form_class=CustomPasswordResetForm,
            extra_email_context={
                "domain": "10.100.100.150",
                "protocol": "http",
                "site_name": "Microcom Approval System",
            },
        ),
        name="password_reset",
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="auth/password_reset_done.html"
        ),
        name="password_reset_done",
    ),

    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="auth/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),

    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="auth/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
