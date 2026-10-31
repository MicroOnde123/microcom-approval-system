from django.urls import path
from . import views
from . import return_note_views as return_notes

app_name = "invoicing"
urlpatterns = [
    path("<int:invoice_id>/return-notes/", return_notes.history, name="return_note_history"),
    path("<int:invoice_id>/return-notes/new/", return_notes.select, name="return_note_select"),
    path("<int:invoice_id>/return-notes/preview/", return_notes.preview, name="return_note_preview"),
    path("<int:invoice_id>/return-notes/issue/", return_notes.issue, name="return_note_issue"),
    path("return-notes/<int:note_id>/", return_notes.detail, name="return_note_detail"),
    path("return-notes/<int:note_id>/print/", return_notes.pdf, name="return_note_print"),
    path("return-notes/<int:note_id>/pdf/<str:language>/", return_notes.pdf, name="return_note_pdf"),
    path("return-note-documents/<int:artifact_id>/download/", return_notes.download, name="return_note_download"),
    path("",views.invoice_list,name="list"),
    path("print-selected/",views.invoice_bulk_print,name="bulk_print"),
    path("request/<int:request_id>/create/",views.invoice_create,name="create"),
    path("<int:pk>/",views.invoice_detail,name="detail"),
    path("<int:pk>/edit/",views.invoice_edit,name="edit"),
    path("<int:pk>/refresh/",views.invoice_refresh,name="refresh"),
    path("<int:pk>/finalize/",views.invoice_finalize,name="finalize"),
    path("<int:pk>/print/",views.invoice_print,name="print"),
    path("<int:pk>/pdf/<str:language>/",views.invoice_pdf,name="pdf"),
    path("documents/<int:artifact_id>/download/",views.invoice_download,name="download"),
]
