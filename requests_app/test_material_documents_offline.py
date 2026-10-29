"""Database-free checks; these do not prove PostgreSQL concurrency/guards."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.template.loader import get_template
from django.test import RequestFactory
from django.utils.translation import override, gettext

from . import material_documents as service
from . import views

ROOT = Path(__file__).resolve().parents[1]


class MaterialDocumentOfflineTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=7, is_authenticated=True, is_superuser=False, can_manage_stock=False)
        self.req = MagicMock(pk=4, submitted_by_id=7, status="APPROVED", stock_deducted=True)
        self.req.request_type.requires_materials = True
        self.req.material_items.exists.return_value = True
        self.req.approvals.filter.return_value.exists.return_value = False

    def test_format_and_expansion(self):
        self.assertEqual(service.format_reference("BC", 2026, 1), "BC/0001/2026")
        self.assertEqual(service.format_reference("BS", 2027, 10000), "BS/10000/2027")
        self.assertEqual(service.format_reference("BC", 2027, service.MAX_COUNTER), f"BC/{service.MAX_COUNTER}/2027")

    def test_invalid_reference(self):
        for args in [("FAC",2026,1),("BC",0,1),("BS",2026,0),("BC",2026,service.MAX_COUNTER+1)]:
            with self.assertRaises(ValidationError): service.format_reference(*args)

    def test_eligible_submitter(self):
        service.validate_access(self.req, self.user)

    def test_both_eligibility_flags_required(self):
        for status,deducted in [("DRAFT",False),("IN_REVIEW",True),("APPROVED",False)]:
            self.req.status=status;self.req.stock_deducted=deducted
            with self.assertRaises(ValidationError):service.validate_access(self.req,self.user)

    def test_material_type_and_rows_required(self):
        self.req.request_type.requires_materials=False
        with self.assertRaises(ValidationError):service.validate_access(self.req,self.user)
        self.req.request_type.requires_materials=True;self.req.material_items.exists.return_value=False
        with self.assertRaises(ValidationError):service.validate_access(self.req,self.user)

    def test_unrelated_user_denied(self):
        self.req.submitted_by_id=8
        with self.assertRaises(PermissionDenied):service.validate_access(self.req,self.user)

    def test_stock_manager_and_assigned_approver(self):
        self.req.submitted_by_id=8;self.user.can_manage_stock=True
        service.validate_access(self.req,self.user)
        self.user.can_manage_stock=False;self.req.approvals.filter.return_value.exists.return_value=True
        service.validate_access(self.req,self.user)

    def test_anonymous_denied(self):
        self.user.is_authenticated=False
        with self.assertRaises(PermissionDenied):service.validate_access(self.req,self.user)

    def issue(self, existing=None, allocation=(2026,1,datetime(2026,10,28,tzinfo=timezone.utc))):
        with patch.object(service.Request,"objects") as requests, patch.object(service.MaterialDocument,"objects") as documents, patch.object(service,"connection") as conn:
            requests.select_for_update.return_value.select_related.return_value.get.return_value=self.req
            documents.filter.return_value.first.return_value=existing
            conn.vendor="postgresql";conn.cursor.return_value.__enter__.return_value.fetchone.return_value=allocation
            result=service.issue_document.__wrapped__(4,"BC",self.user)
            return result,documents,conn

    def test_exact_reprint_does_not_allocate(self):
        record=object();result,documents,conn=self.issue(existing=record)
        self.assertIs(result,record);conn.cursor.assert_not_called();documents.create.assert_not_called()

    def test_database_clock_and_atomic_upsert(self):
        _,documents,conn=self.issue()
        sql=conn.cursor.return_value.__enter__.return_value.execute.call_args.args[0]
        self.assertIn("Africa/Kinshasa",sql);self.assertIn("clock_timestamp()",sql)
        self.assertIn("ON CONFLICT (kind, year)",sql)
        self.assertEqual(documents.create.call_args.kwargs['reference'],"BC/0001/2026")

    def test_exhaustion_fails(self):
        with self.assertRaises(ValidationError):self.issue(allocation=None)

    def test_service_has_no_stock_or_financial_operations(self):
        text=(ROOT/'requests_app/material_documents.py').read_text()
        self.assertNotIn('deduct_material_stock',text);self.assertNotIn('StockMovement',text)
        self.assertNotIn('invoicing',text)

    def test_get_confirmation_does_not_issue(self):
        self.req.material_documents.filter.return_value.first.return_value=None
        request=RequestFactory().get('/');request.user=self.user
        with patch.object(views,'get_object_or_404',return_value=self.req),patch.object(views,'issue_document') as issue,patch.object(views,'render',return_value='confirmation'):
            self.assertEqual(views.material_document(request,4,'BC'),'confirmation')
            issue.assert_not_called()

    def test_post_redirects_and_uses_service(self):
        request=RequestFactory().post('/');request.user=self.user
        with patch.object(views,'get_object_or_404',return_value=self.req),patch.object(views,'issue_document') as issue:
            response=views.material_document(request,4,'BS')
            self.assertEqual(response.status_code,302);issue.assert_called_once_with(4,'BS',self.user)

    def test_blocked_view_does_not_issue(self):
        request=RequestFactory().post('/');request.user=self.user;self.req.stock_deducted=False
        with patch.object(views,'get_object_or_404',return_value=self.req),patch.object(views,'issue_document') as issue:
            self.assertEqual(views.material_document(request,4,'BS').status_code,409);issue.assert_not_called()

    def test_layout_is_shared_and_localized(self):
        req=SimpleNamespace(request_number='REQ-LEGACY',status='APPROVED',finalized_at=None,submitted_at=None,
            submitted_by=SimpleNamespace(full_name='<script>unsafe</script>',username='synthetic'),department='Existing',
            request_for_department='Existing',date_needed=None,material_items=SimpleNamespace(all=[]),
            description='Same information',material_issue_note='Same note')
        template=get_template('requests_app/partials/approved_document_copy.html')
        for language in ('en','fr'):
            with override(language):
                outputs=[]
                for kind,title in [('BC',gettext('Material Order')),('BS',gettext('Material Exit Slip'))]:
                    text=template.render({'request_obj':req,'approvals':[], 'material_document':SimpleNamespace(reference=kind+'/0001/2026'),'material_document_title':title})
                    self.assertIn(title,text);self.assertNotIn('<script>',text)
                    outputs.append(text.replace(title,'TITLE').replace(kind+'/0001/2026','REFERENCE'))
                self.assertEqual(*outputs)

    def test_translations(self):
        with override('fr'):
            for text in ['Material Order','Print BC — Material Order','Print BS — Material Exit Slip','Document No:',"Prepare and print","Material documents require final approval and confirmed stock deduction."]:
                self.assertNotEqual(gettext(text),text)

    def test_csrf_rejects_unprotected_post(self):
        from django.middleware.csrf import CsrfViewMiddleware
        request=RequestFactory().post('/requests/4/material-documents/BC/')
        request.user=self.user
        response=CsrfViewMiddleware(lambda request: None).process_view(request,views.material_document,(),{})
        self.assertEqual(response.status_code,403)

    def test_confirmation_presentation_both_kinds_and_languages(self):
        from django.contrib.auth.models import AnonymousUser
        request=RequestFactory().get('/');request.user=AnonymousUser()
        template=get_template('requests_app/material_document_confirm.html')
        for language in ('en','fr'):
            with override(language):
                for kind,label in [('BC','Purchase Order (BC)'),('BS','Material Issue Note (BS)')]:
                    text=template.render({'kind':kind,'request_obj':SimpleNamespace(request_number='<unsafe>REQ-001'),
                        'back_url':'/requests/4/','csrf_token':'synthetic-csrf','request':request})
                    self.assertIn(gettext(label),text)
                    self.assertIn(gettext('Printing does not deduct stock or modify inventory.'),text)
                    self.assertIn(gettext('Confirm & Print'),text)
                    self.assertIn(gettext('Cancel'),text)
                    self.assertIn('href="/requests/4/"',text)
                    self.assertIn('method="post"',text)
                    self.assertIn('name="csrfmiddlewaretoken"',text)
                    self.assertIn('&lt;unsafe&gt;REQ-001',text)
                    self.assertNotIn('<unsafe>',text)
                    self.assertIn('@media (max-width: 540px)',text)
                    self.assertIn(':focus-visible',text)
        with override('fr'):
            self.assertEqual(gettext('Confirm & Print'),'Confirmer et imprimer')
            self.assertEqual(gettext('Purchase Order (BC)'),'Bon de Commande (BC)')

    def test_legacy_administration_template_title_unchanged(self):
        req=SimpleNamespace(submitted_by=SimpleNamespace(username='synthetic',full_name=''), description='Legacy administration', material_items=SimpleNamespace(all=[]))
        text=get_template('requests_app/partials/approved_document_copy.html').render({'request_obj':req})
        self.assertIn('Material Exit Slip',text)
        self.assertNotIn('Document No:',text)

    def test_migration_is_additive_and_protects_reversal(self):
        import importlib
        migration=importlib.import_module('requests_app.migrations.0019_materialdocumentsequence_materialdocument')
        self.assertEqual([type(op).__name__ for op in migration.Migration.operations],['CreateModel','CreateModel','RunSQL','RunPython'])
        self.assertIn('immutable',migration.GUARDS)
        self.assertNotIn('invoicing_',migration.GUARDS)
