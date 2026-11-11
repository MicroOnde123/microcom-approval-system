"""Fresh isolated PostgreSQL only; append-only test data retained until DB disposal.

SimpleTestCase is intentional: outermost durable services and actual concurrent
commits cannot run inside TestCase rollback wrappers. Unique fixture namespaces
avoid TRUNCATE/flush of immutable ledgers. Run only in a disposable test database.
"""
import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier,Event
from uuid import uuid4
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import signing
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import connection,connections,transaction,IntegrityError,close_old_connections
from django.test import SimpleTestCase,override_settings,Client
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.utils.translation import override
from accounts.models import Department
from core.models import CompanyDocumentSettings
from inventory.models import Material,MaterialCategory,Succursale
from requests_app.models import Request,RequestType,RequestMaterialItem,StockMovement
from requests_app.services import submit_request,approve_step
from requests_app.stock_services import return_material_stock,RETURN_TOKEN_SALT
from workflows.models import ApprovalWorkflow,ApprovalWorkflowStep
from .models import Invoice,CompanyVerification,DocumentSequence,AdjustedInvoiceStatement
from .configuration import business_date
from .services import create_draft,edit_draft,finalize_invoice,draft_revision,database_now,refresh_draft
from . import return_note_services as br
from . import adjusted_services as service
from .adjusted_access import navigation
from .adjusted_pdf import render

@override_settings(ADJUSTED_INVOICE_STATEMENTS_ENABLED=True,MATERIAL_RETURN_NOTE_UI_ENABLED=True)
class AdjustedStatementTests(SimpleTestCase):
    databases={'default'}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor!='postgresql' or not connection.settings_dict['NAME'].startswith('test_'):
            raise unittest.SkipTest('Disposable isolated PostgreSQL test database required')

    def setUp(self):
        key=uuid4().hex[:12]
        self.dept=Department.objects.create(code=key,name='Fictional training '+key)
        User=get_user_model()
        self.admin=User.objects.create_superuser(username='admin-'+key,password='test-only')
        self.user=User.objects.create_user(username='stock-'+key,department=self.dept,can_manage_stock=True)
        perms=['view_invoice','add_invoice','change_invoice','finalize_invoice','view_materialreturnnote','add_materialreturnnote',
            'issue_materialreturnnote','view_materialreturnnote_document','view_adjustedinvoicestatement',
            'issue_adjustedinvoicestatement','document_adjustedinvoicestatement']
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='invoicing',codename__in=perms))
        self.category=MaterialCategory.objects.create(code=key,name=key)
        self.material=Material.objects.create(code=key,name='Fictional training switch',category=self.category,unit='pcs',stock_quantity=100)
        self.branch=Succursale.objects.create(code=key,name='Fictional branch',physical_address='100 Demonstration Avenue')
        kind=RequestType.objects.create(code=key,name=key,requires_materials=True)
        flow=ApprovalWorkflow.objects.create(name=key,request_type=kind)
        ApprovalWorkflowStep.objects.create(workflow=flow,step_order=1,approver_user=self.user,is_stock_review=True)
        self.req=Request.objects.create(request_number=str(uuid4()),submitted_by=self.user,department=self.dept,request_type=kind,description='Synthetic statement validation')
        self.item=RequestMaterialItem.objects.create(request=self.req,material=self.material,quantity=10)
        submit_request(self.req);approve_step(self.req.approvals.get(),self.user,classification='MICROCOM',succursale=self.branch)
        config=CompanyDocumentSettings.objects.first()
        if config is None:
            config=CompanyDocumentSettings.objects.create(company_name='MICROCOM TRAINING',company_address='Fictional training address',contact_details='training@example.invalid')
            CompanyVerification.attest(config,self.admin)
        self.year=business_date(database_now(),'Africa/Kinshasa').year
        for kind,prefix in [('INVOICE','FAC'),('RETURN_NOTE','BR'),('ADJUSTED','EAR')]:
            seq=DocumentSequence.objects.filter(document_type=kind,year=self.year,series='MAIN').first()
            if seq is None:
                seq=DocumentSequence.objects.create(document_type=kind,year=self.year,series='MAIN',number_format=prefix+'/{number:06d}/{year}')
                seq.attest(self.admin,'Fictional numbering verification')
        self.invoice=None

    def invoice_ready(self,pre_return=0,price='100',currency='USD'):
        if pre_return:self.physical(pre_return)
        invoice=create_draft(self.req.pk,self.user,currency=currency)
        edit_draft(invoice.pk,self.user,prices={l.pk:Decimal(price) for l in invoice.lines.all()},note='Synthetic price',revision=draft_revision(invoice,self.user))
        invoice.refresh_from_db()
        self.invoice=finalize_invoice(invoice.pk,self.user,revision=draft_revision(invoice,self.user))
        return self.invoice

    def physical(self,quantity):
        token=signing.dumps({'item':self.item.pk,'user':self.user.pk,'operation':str(uuid4())},salt=RETURN_TOKEN_SALT)
        return return_material_stock(self.item.pk,self.user,Decimal(str(quantity)),'Fictional unused material',token)[0]

    def return_note(self,quantity):
        move=self.physical(quantity)
        preview=br.preview_material_return_note(self.invoice.pk,self.user,return_movement_ids=[move.pk],reason='Synthetic return')
        return br.issue_material_return_note(self.invoice.pk,self.user,return_movement_ids=[move.pk],reason='Synthetic return',
            issuance_token=preview['issuance_token'],confirmation=preview['confirmation'])

    def statement(self):
        _,token=service.preview(self.invoice.pk,self.user)
        return service.issue(self.invoice.pk,self.user,confirmation=token)

    def test_no_br_preview_and_issue_not_available(self):
        self.invoice_ready();snapshot=service.reconciliation(self.invoice.pk,self.user)
        self.assertEqual(snapshot['returns'],[])
        with self.assertRaises(ValidationError):service.preview(self.invoice.pk,self.user)

    def test_one_return_1000_200_800(self):
        self.invoice_ready();self.return_note(2);s=self.statement()
        self.assertEqual(tuple(Decimal(s.snapshot[k]) for k in ('original_total','returned_total','net_total')),(1000,200,800))

    def test_multiple_returns_1000_300_700(self):
        self.invoice_ready();self.return_note(2);first=self.statement();self.return_note(1);second=self.statement()
        line=second.snapshot['lines'][0]
        self.assertEqual(tuple(Decimal(line[k]) for k in ('original_quantity','returned_quantity','net_quantity')),(10,3,7))
        self.assertEqual(Decimal(second.snapshot['net_total']),700);self.assertEqual(len(second.snapshot['returns']),2)
        first.refresh_from_db();self.assertEqual(Decimal(first.snapshot['net_total']),800)
        self.invoice.refresh_from_db();self.assertEqual(self.invoice.total,1000)

    def test_pre_invoice_returns_are_excluded_once(self):
        self.invoice_ready(pre_return=3);self.return_note(2);s=self.statement()
        self.assertEqual(Decimal(s.snapshot['original_total']),700)
        self.assertEqual(Decimal(s.snapshot['net_total']),500)
        self.assertEqual(Decimal(s.snapshot['lines'][0]['original_quantity']),7)

    def test_return_while_draft_requires_existing_refresh(self):
        inv=create_draft(self.req.pk,self.user,currency='USD')
        edit_draft(inv.pk,self.user,prices={l.pk:Decimal(100) for l in inv.lines.all()},note='Synthetic',revision=draft_revision(inv,self.user));inv.refresh_from_db()
        self.physical(3)
        with self.assertRaises(ValidationError):finalize_invoice(inv.pk,self.user,revision=draft_revision(inv,self.user))
        refresh_draft(inv.pk,self.user,revision=draft_revision(inv,self.user));inv.refresh_from_db()
        self.assertEqual(finalize_invoice(inv.pk,self.user,revision=draft_revision(inv,self.user)).total,700)

    def test_preview_does_not_allocate_number(self):
        self.invoice_ready();self.return_note(2)
        seq=DocumentSequence.objects.get(document_type='ADJUSTED',year=self.year,series='MAIN');before=seq.next_counter
        service.preview(self.invoice.pk,self.user);seq.refresh_from_db();self.assertEqual(seq.next_counter,before)
        self.assertFalse(self.invoice.adjusted_statements.exists())

    def test_repeated_submission_is_idempotent(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user)
        a=service.issue(self.invoice.pk,self.user,confirmation=token);b=service.issue(self.invoice.pk,self.user,confirmation=token)
        self.assertEqual(a.pk,b.pk);self.assertEqual(self.invoice.adjusted_statements.count(),1)

    def test_changed_br_invalidates_preview(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user);self.return_note(1)
        with self.assertRaises(ValidationError):service.issue(self.invoice.pk,self.user,confirmation=token)

    def test_confirmation_tampering_is_rejected(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user)
        with self.assertRaises(ValidationError):service.issue(self.invoice.pk,self.user,confirmation=token+'x')

    def test_model_and_database_immutability(self):
        self.invoice_ready();self.return_note(2);s=self.statement()
        with self.assertRaises(ValidationError):s.save()
        with self.assertRaises(ValidationError):s.delete()
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c:c.execute('UPDATE invoicing_adjustedinvoicestatement SET number=%s WHERE id=%s',['changed',s.pk])
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c:c.execute('DELETE FROM invoicing_adjustedinvoicestatement WHERE id=%s',[s.pk])

    def test_stock_and_invoice_unchanged_by_statement(self):
        self.invoice_ready();self.return_note(2)
        self.material.refresh_from_db();original_stock=self.material.stock_quantity
        stock=list(StockMovement.objects.filter(request=self.req).values());before=list(Invoice.objects.filter(pk=self.invoice.pk).values())
        self.statement()
        self.assertEqual(stock,list(StockMovement.objects.filter(request=self.req).values()))
        self.assertEqual(before,list(Invoice.objects.filter(pk=self.invoice.pk).values()))
        self.material.refresh_from_db();self.assertEqual(self.material.stock_quantity,original_stock)

    def test_overreturn_is_blocked(self):
        self.invoice_ready();self.return_note(10)
        with self.assertRaises(ValidationError):self.physical(1)
        self.assertEqual(Decimal(self.statement().snapshot['net_total']),0)

    def test_read_issue_document_permissions_separate(self):
        self.invoice_ready();self.return_note(2);s=self.statement()
        for perm,call in [('issue_adjustedinvoicestatement',lambda:service.preview(self.invoice.pk,self.user)),
                          ('document_adjustedinvoicestatement',lambda:service.get_statement(s.pk,self.user,document=True)),
                          ('view_adjustedinvoicestatement',lambda:service.reconciliation(self.invoice.pk,self.user))]:
            permission=Permission.objects.get(content_type__app_label='invoicing',codename=perm);self.user.user_permissions.remove(permission)
            with self.assertRaises(PermissionDenied):call()
            self.user.user_permissions.add(permission)

    def test_request_scope_enforced(self):
        self.invoice_ready();self.return_note(2)
        outsider=get_user_model().objects.create_user(username=uuid4().hex,department=self.dept)
        outsider.user_permissions.add(*self.user.user_permissions.all())
        with self.assertRaises(PermissionDenied):service.reconciliation(self.invoice.pk,outsider)

    def test_disabled_routes_and_navigation_make_no_queries(self):
        self.invoice_ready()
        with override_settings(ADJUSTED_INVOICE_STATEMENTS_ENABLED=False),CaptureQueriesContext(connection) as queries:
            self.assertEqual(navigation(self.user,self.invoice),{})
            self.assertEqual(Client().get(reverse('invoicing:adjusted_overview',args=[self.invoice.pk])).status_code,404)
        self.assertEqual(len(queries),0)

    def test_rounding_uses_stored_br_values(self):
        self.invoice_ready(price='0.0050');self.return_note(1);self.return_note(1);s=self.statement()
        self.assertEqual(Decimal(s.snapshot['returned_total']),Decimal('.01'))
        self.assertEqual(Decimal(s.snapshot['net_total']),Decimal('.04'))

    def test_bilingual_pdf_and_historical_values(self):
        from pypdf import PdfReader
        self.invoice_ready();self.return_note(2);s=self.statement();self.return_note(1)
        for lang,title in [('en','Adjusted Invoice Statement'),('fr','État récapitulatif après retours')]:
            content=render(s,lang);self.assertTrue(content.startswith(b'%PDF'))
            text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)
            self.assertIn(title,text);self.assertIn('800.00',text);self.assertIn(s.number,text)

    def test_bilingual_ui_history_and_protected_download(self):
        self.invoice_ready();self.return_note(2);s=self.statement();client=Client();client.force_login(self.user)
        for lang,title in [('en','Adjusted Invoice Statements'),('fr','États récapitulatifs après retours')]:
            client.cookies['django_language']=lang
            response=client.get(reverse('invoicing:adjusted_overview',args=[self.invoice.pk]));self.assertContains(response,title)
        response=client.post(reverse('invoicing:adjusted_download',args=[s.pk]));self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response['Content-Disposition']);response.close()
        self.assertEqual(client.get(reverse('invoicing:adjusted_print',args=[s.pk])).status_code,405)

    def _thread(self,call):
        close_old_connections()
        try:return call()
        finally:connections['default'].close()

    def test_concurrent_same_token_commits_once(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user);barrier=Barrier(2)
        def work():
            barrier.wait();return service.issue(self.invoice.pk,self.user,confirmation=token).pk
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(lambda _:self._thread(work),range(2)))
        self.assertEqual(values[0],values[1]);self.assertEqual(self.invoice.adjusted_statements.count(),1)

    def test_concurrent_separate_previews_return_one_statement(self):
        self.invoice_ready();self.return_note(2);tokens=[service.preview(self.invoice.pk,self.user)[1] for _ in range(2)];barrier=Barrier(2)
        def work(token):barrier.wait();return service.issue(self.invoice.pk,self.user,confirmation=token).number
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(lambda token:self._thread(lambda:work(token)),tokens))
        self.assertEqual(values[0],values[1])
        self.assertEqual(self.invoice.adjusted_statements.count(),1)

    def test_br_concurrent_with_statement_yields_consistent_snapshot(self):
        self.invoice_ready();self.return_note(2);move=self.physical(1)
        bp=br.preview_material_return_note(self.invoice.pk,self.user,return_movement_ids=[move.pk],reason='Concurrent return')
        _,token=service.preview(self.invoice.pk,self.user);barrier=Barrier(2)
        def statement_work():
            barrier.wait()
            try:return service.issue(self.invoice.pk,self.user,confirmation=token)
            except ValidationError:return None
        def br_work():
            barrier.wait();return br.issue_material_return_note(self.invoice.pk,self.user,return_movement_ids=[move.pk],reason='Concurrent return',issuance_token=bp['issuance_token'],confirmation=bp['confirmation'])
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(self._thread,statement_work);b=pool.submit(self._thread,br_work);s=a.result();b.result()
        if s:self.assertEqual(Decimal(s.snapshot['net_total']),800)
        self.assertEqual(Decimal(service.reconciliation(self.invoice.pk,self.user)['net_total']),700)

    def test_forged_snapshot_rejected_by_database(self):
        import json
        self.invoice_ready();self.return_note(2);a=self.statement()
        seq=DocumentSequence.objects.get(pk=a.sequence_id);counter=seq.next_counter
        with self.assertRaises(IntegrityError),transaction.atomic():
            seq.next_counter+=1;seq.save(update_fields=['next_counter'])
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO invoicing_adjustedinvoicestatement
                  (invoice_id,sequence_id,sequence_counter,number,issued_at,issue_date,issued_by_id,issuer_name,operation_token,confirmation_digest,snapshot)
                  SELECT invoice_id,sequence_id,%s,%s,clock_timestamp(),issue_date,issued_by_id,issuer_name,%s,confirmation_digest,%s::jsonb
                  FROM invoicing_adjustedinvoicestatement WHERE id=%s""",
                  [counter,'FORGED-'+uuid4().hex,str(uuid4()),json.dumps({**a.snapshot,'net_total':'1.00'}),a.pk])

    def test_missing_unverified_sequence_does_not_consume_numbers(self):
        self.invoice_ready();self.return_note(2)
        _,token=service.preview(self.invoice.pk,self.user,series='MISSING')
        with self.assertRaises(ValidationError):service.issue(self.invoice.pk,self.user,confirmation=token)
        seq=DocumentSequence.objects.create(document_type='ADJUSTED',year=self.year,series=uuid4().hex[:20],number_format='EAR/{number}/{year}')
        _,token=service.preview(self.invoice.pk,self.user,series=seq.series)
        with self.assertRaises(ValidationError):service.issue(self.invoice.pk,self.user,confirmation=token)
        seq.refresh_from_db();self.assertEqual(seq.next_counter,1)

    def test_csrf_and_document_permission_enforced(self):
        self.invoice_ready();self.return_note(2);s=self.statement()
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(reverse('invoicing:adjusted_issue',args=[self.invoice.pk]),{}).status_code,403)
        permission=Permission.objects.get(content_type__app_label='invoicing',codename='document_adjustedinvoicestatement')
        self.user.user_permissions.remove(permission)
        client=Client();client.force_login(self.user)
        self.assertEqual(client.post(reverse('invoicing:adjusted_download',args=[s.pk])).status_code,403)

    def test_cross_invoice_confirmation_is_rejected(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user)
        binding=signing.loads(token,salt=service.SALT);binding['invoice']+=1000000
        with self.assertRaises(ValidationError):service.issue(self.invoice.pk,self.user,confirmation=signing.dumps(binding,salt=service.SALT))

    def test_issued_sequence_identity_is_frozen(self):
        self.invoice_ready();self.return_note(2);s=self.statement()
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c:c.execute('UPDATE invoicing_documentsequence SET number_format=%s WHERE id=%s',['CHANGED/{number}/{year}',s.sequence_id])

    def test_eur_currency_preserved(self):
        self.invoice_ready(currency='EUR');self.return_note(2);s=self.statement()
        self.assertEqual(s.snapshot['currency'],'EUR');self.assertEqual(Decimal(s.snapshot['net_total']),800)

    def test_cdf_currency_preserved(self):
        self.invoice_ready(currency='CDF');self.return_note(2);s=self.statement()
        self.assertEqual(s.snapshot['currency'],'CDF');self.assertEqual(Decimal(s.snapshot['net_total']),800)

    def test_expired_uncommitted_confirmation_rejected(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user)
        with patch.object(service,'MAX_AGE',-1),self.assertRaises(ValidationError):service.issue(self.invoice.pk,self.user,confirmation=token)

    def test_expired_committed_retry_returns_original(self):
        self.invoice_ready();self.return_note(2);_,token=service.preview(self.invoice.pk,self.user)
        a=service.issue(self.invoice.pk,self.user,confirmation=token)
        with patch.object(service,'MAX_AGE',-1):self.assertEqual(service.issue(self.invoice.pk,self.user,confirmation=token).pk,a.pk)

    def test_every_disabled_route_returns_404_without_queries(self):
        routes=[('adjusted_overview',1),('adjusted_issue',1),('adjusted_detail',1),('adjusted_print',1),('adjusted_download',1)]
        with override_settings(ADJUSTED_INVOICE_STATEMENTS_ENABLED=False),CaptureQueriesContext(connection) as queries:
            for route,pk in routes:
                self.assertEqual(Client().post(reverse('invoicing:'+route,args=[pk])).status_code,404)
        self.assertEqual(len(queries),0)

    def test_draft_invoice_cannot_be_reconciled(self):
        invoice=create_draft(self.req.pk,self.user,currency='USD')
        with self.assertRaises(ValidationError):service.reconciliation(invoice.pk,self.user)

    def test_separate_previews_reuse_reference_without_consuming_counter(self):
        self.invoice_ready();self.return_note(2)
        first_token=service.preview(self.invoice.pk,self.user)[1]
        second_token=service.preview(self.invoice.pk,self.user)[1]
        self.assertNotEqual(first_token,second_token)
        a=service.issue(self.invoice.pk,self.user,confirmation=first_token)
        seq=DocumentSequence.objects.get(pk=a.sequence_id);counter=seq.next_counter
        b=service.issue(self.invoice.pk,self.user,confirmation=second_token)
        seq.refresh_from_db()
        self.assertEqual((a.pk,a.number),(b.pk,b.number));self.assertEqual(seq.next_counter,counter)
        self.assertEqual(self.invoice.adjusted_statements.count(),1)

    def test_new_preview_of_existing_state_reuses_original_even_other_series(self):
        self.invoice_ready();self.return_note(2);a=self.statement()
        _,token=service.preview(self.invoice.pk,self.user,series='NO_SEQUENCE_NEEDED')
        self.assertEqual(service.issue(self.invoice.pk,self.user,confirmation=token).pk,a.pk)

    def test_duplicate_state_retry_after_new_br_and_expiry_returns_history(self):
        self.invoice_ready();self.return_note(2)
        _,first=service.preview(self.invoice.pk,self.user);_,second=service.preview(self.invoice.pk,self.user)
        a=service.issue(self.invoice.pk,self.user,confirmation=first)
        self.return_note(1);b=self.statement()
        with patch.object(service,'MAX_AGE',-1):
            self.assertEqual(service.issue(self.invoice.pk,self.user,confirmation=second).pk,a.pk)
            self.assertEqual(service.issue(self.invoice.pk,self.user,confirmation=first).pk,a.pk)
        self.assertNotEqual(a.pk,b.pk)
        self.assertEqual(Decimal(a.snapshot['net_total']),800);self.assertEqual(Decimal(b.snapshot['net_total']),700)
        self.assertEqual(self.invoice.adjusted_statements.count(),2)

    def test_database_index_blocks_duplicate_even_with_new_token_and_number(self):
        self.invoice_ready();self.return_note(2);a=self.statement()
        seq=DocumentSequence.objects.get(pk=a.sequence_id);before=seq.next_counter
        # A raw INSERT bypasses model validation and the service coordinator;
        # the database's unique state index must still reject it atomically.
        with self.assertRaises(IntegrityError) as caught:
            with transaction.atomic():
                seq.next_counter+=1;seq.save(update_fields=['next_counter'])
                with connection.cursor() as cursor:
                    cursor.execute("""INSERT INTO invoicing_adjustedinvoicestatement
                      (invoice_id,sequence_id,sequence_counter,number,issued_at,issue_date,issued_by_id,issuer_name,operation_token,confirmation_digest,snapshot)
                      SELECT invoice_id,sequence_id,%s,%s,clock_timestamp(),issue_date,issued_by_id,issuer_name,%s,confirmation_digest,snapshot
                      FROM invoicing_adjustedinvoicestatement WHERE id=%s""",
                      [before,'DUPLICATE-'+uuid4().hex,str(uuid4()),a.pk])
        self.assertEqual(caught.exception.__cause__.diag.constraint_name,'as_invoice_state_unique')
        seq.refresh_from_db();self.assertEqual(seq.next_counter,before)
        self.assertEqual(self.invoice.adjusted_statements.count(),1)

    def test_state_identity_ignores_br_order_and_timestamp_formatting(self):
        from copy import deepcopy
        self.invoice_ready();self.return_note(2);self.return_note(1)
        snapshot=service.reconciliation(self.invoice.pk,self.user);other=deepcopy(snapshot)
        other['returns'].reverse()
        for note in other['returns']:note['issued_at']='Different presentation of the same immutable timestamp'
        self.assertEqual(service._state_key(snapshot),service._state_key(other))

    def test_deduplicated_state_requires_current_issue_permission(self):
        self.invoice_ready();self.return_note(2);a=self.statement()
        _,token=service.preview(self.invoice.pk,self.user)
        permission=Permission.objects.get(content_type__app_label='invoicing',codename='issue_adjustedinvoicestatement')
        self.user.user_permissions.remove(permission)
        with self.assertRaises(PermissionDenied):service.issue(self.invoice.pk,self.user,confirmation=token)
        self.assertEqual(self.invoice.adjusted_statements.count(),1)

    def test_bilingual_duplicate_submission_displays_same_statement_and_pdf(self):
        self.invoice_ready();self.return_note(2);client=Client();client.force_login(self.user)
        for language in ('en','fr'):
            client.cookies['django_language']=language
            _,first=service.preview(self.invoice.pk,self.user);_,second=service.preview(self.invoice.pk,self.user)
            a=service.issue(self.invoice.pk,self.user,confirmation=first)
            response=client.post(reverse('invoicing:adjusted_issue',args=[self.invoice.pk]),{'confirmation':second,'confirmed':'on'})
            self.assertRedirects(response,reverse('invoicing:adjusted_detail',args=[a.pk]))
            self.assertEqual(self.invoice.adjusted_statements.count(),1)
            response=client.post(reverse('invoicing:adjusted_download',args=[a.pk]));self.assertEqual(response.status_code,200);response.close()

    def test_new_zero_value_br_changes_state_without_repricing(self):
        self.invoice_ready(price='0');self.return_note(1);a=self.statement()
        self.return_note(1);b=self.statement()
        self.assertNotEqual(a.pk,b.pk)
        self.assertEqual(Decimal(a.snapshot['net_total']),0);self.assertEqual(Decimal(b.snapshot['net_total']),0)
        self.assertEqual(Decimal(b.snapshot['lines'][0]['returned_quantity']),2)

    def test_another_authorized_issuer_reuses_original_issuer_and_reference(self):
        self.invoice_ready();self.return_note(2);a=self.statement()
        _,token=service.preview(self.invoice.pk,self.admin)
        b=service.issue(self.invoice.pk,self.admin,confirmation=token)
        self.assertEqual((b.pk,b.number,b.issued_by_id),(a.pk,a.number,self.user.pk))
        self.assertEqual(self.invoice.adjusted_statements.count(),1)
