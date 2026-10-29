"""DEFERRED: authorized disposable PostgreSQL only; never Supabase."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, close_old_connections, transaction, IntegrityError
from django.test import TransactionTestCase

from accounts.models import Department
from inventory.models import Material, MaterialCategory
from .models import Request, RequestType, RequestMaterialItem, StockMovement, MaterialDocument, MaterialDocumentSequence
from .material_documents import issue_document


@contextmanager
def clock(moment):
    def execute(execute, sql, params, many, context):
        if 'WITH instant AS MATERIALIZED (SELECT clock_timestamp()' in sql:
            sql=sql.replace('clock_timestamp()', '%s::timestamptz',1)
            params=[moment,*params]
        return execute(sql,params,many,context)
    with connection.execute_wrapper(execute):yield


class MaterialDocumentPostgreSQLTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL required')
        self.department=Department.objects.create(code='BCBS',name='Synthetic')
        self.user=get_user_model().objects.create_user(username='bcbs-test',department=self.department)
        self.kind=RequestType.objects.create(code='MATERIAL',name='Synthetic',requires_materials=True)
        category=MaterialCategory.objects.create(code='BCBS',name='Synthetic')
        self.material=Material.objects.create(code='BCBS',name='Synthetic',category=category,unit='pcs',stock_quantity=10)
        self.req=self.request('REQ-LEGACY-BCBS')

    def request(self,number):
        req=Request.objects.create(request_number=number,request_type=self.kind,submitted_by=self.user,
            department=self.department,request_for_department=self.department,description='Synthetic',status='APPROVED',stock_deducted=True)
        RequestMaterialItem.objects.create(request=req,material=self.material,quantity=1)
        StockMovement.objects.create(request=req,material=self.material,quantity=1,movement_type='OUT')
        return req

    def test_reprint_independent_counters_and_stock_neutrality(self):
        with clock(datetime(2026,10,28,tzinfo=timezone.utc)):
            bc=issue_document(self.req.pk,'BC',self.user)
            bs=issue_document(self.req.pk,'BS',self.user)
            self.assertEqual(issue_document(self.req.pk,'BC',self.user).pk,bc.pk)
        self.assertEqual(bc.reference,'BC/0001/2026');self.assertEqual(bs.reference,'BS/0001/2026')
        self.assertEqual(MaterialDocument.objects.count(),2)
        self.assertEqual(StockMovement.objects.count(),1)
        self.material.refresh_from_db();self.assertEqual(self.material.stock_quantity,Decimal('10'))
        self.req.refresh_from_db();self.assertEqual(self.req.request_number,'REQ-LEGACY-BCBS')

    def test_confirmation_get_cancel_csrf_post_and_reprint(self):
        from django.test import Client
        from django.urls import reverse
        from invoicing.models import Invoice, DocumentSequence
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        before_invoices=list(Invoice.objects.values())
        before_financial_sequences=list(DocumentSequence.objects.values())
        for kind in ('BC','BS'):
            url=reverse('material_document',args=[self.req.pk,kind])
            response=client.get(url)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'Confirm & Print')
            self.assertFalse(MaterialDocument.objects.filter(request=self.req,kind=kind).exists())
            self.assertEqual(client.post(url).status_code,403)
            self.assertEqual(client.get(reverse('request_detail',args=[self.req.pk])).status_code,200)
            self.assertFalse(MaterialDocument.objects.filter(request=self.req,kind=kind).exists())
            token=client.cookies['csrftoken'].value
            self.assertEqual(client.post(url,{'csrfmiddlewaretoken':token}).status_code,302)
            reference=MaterialDocument.objects.get(request=self.req,kind=kind).reference
            self.assertEqual(client.get(url).status_code,200)
            self.assertEqual(MaterialDocument.objects.get(request=self.req,kind=kind).reference,reference)
        self.assertEqual(StockMovement.objects.filter(request=self.req).count(),1)
        self.material.refresh_from_db();self.assertEqual(self.material.stock_quantity,Decimal('10'))
        self.assertEqual(before_invoices,list(Invoice.objects.values()))
        self.assertEqual(before_financial_sequences,list(DocumentSequence.objects.values()))

    def test_concurrent_same_request_allocates_once(self):
        barrier=Barrier(4)
        def worker(_):
            close_old_connections()
            try:
                user=get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=15)
                return issue_document(self.req.pk,'BS',user).reference
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:refs=list(pool.map(worker,range(4)))
        self.assertEqual(len(set(refs)),1);self.assertEqual(MaterialDocument.objects.count(),1)
        self.assertEqual(MaterialDocumentSequence.objects.get().last_counter,1)

    def test_concurrent_first_use_different_requests(self):
        other=self.request('REQ-LEGACY-BCBS-2');barrier=Barrier(2)
        def worker(pk):
            close_old_connections()
            try:
                user=get_user_model().objects.get(pk=self.user.pk);barrier.wait(timeout=15)
                return issue_document(pk,'BC',user).counter
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:counters=list(pool.map(worker,[self.req.pk,other.pk]))
        self.assertEqual(sorted(counters),[1,2])

    def test_kinshasa_year_boundary(self):
        other=self.request('REQ-LEGACY-BCBS-2')
        with clock(datetime(2026,12,31,22,59,59,tzinfo=timezone.utc)):a=issue_document(self.req.pk,'BC',self.user)
        with clock(datetime(2026,12,31,23,tzinfo=timezone.utc)):b=issue_document(other.pk,'BC',self.user)
        self.assertEqual(a.reference,'BC/0001/2026');self.assertEqual(b.reference,'BC/0001/2027')

    def test_rollback_preserves_counter(self):
        with self.assertRaises(RuntimeError),transaction.atomic():
            issue_document(self.req.pk,'BS',self.user)
            raise RuntimeError('Synthetic rollback')
        self.assertFalse(MaterialDocument.objects.exists());self.assertFalse(MaterialDocumentSequence.objects.exists())

    def test_access_and_eligibility(self):
        other=get_user_model().objects.create_user(username='unrelated-bcbs')
        with self.assertRaises(PermissionDenied):issue_document(self.req.pk,'BC',other)
        for status,deducted in [('DRAFT',True),('APPROVED',False)]:
            Request.objects.filter(pk=self.req.pk).update(status=status,stock_deducted=deducted)
            with self.assertRaises(ValidationError):issue_document(self.req.pk,'BS',self.user)
        self.assertFalse(MaterialDocumentSequence.objects.exists())

    def test_immutable_records_and_counter(self):
        doc=issue_document(self.req.pk,'BS',self.user)
        for operation in [lambda:MaterialDocument.objects.filter(pk=doc.pk).update(reference='BS/9999/2026'),
                lambda:MaterialDocument.objects.filter(pk=doc.pk).delete(),
                lambda:MaterialDocumentSequence.objects.update(last_counter=0),lambda:MaterialDocumentSequence.objects.all().delete()]:
            with self.assertRaises(IntegrityError),transaction.atomic():operation()

    def test_expansion_and_bigint_exhaustion(self):
        MaterialDocumentSequence.objects.create(kind='BC',year=2026,last_counter=9999)
        with clock(datetime(2026,10,28,tzinfo=timezone.utc)):
            self.assertEqual(issue_document(self.req.pk,'BC',self.user).reference,'BC/10000/2026')
        MaterialDocumentSequence.objects.filter(kind='BC').update(last_counter=9223372036854775807)
        other=self.request('REQ-LEGACY-BCBS-2')
        with clock(datetime(2026,10,28,tzinfo=timezone.utc)),self.assertRaises(ValidationError):issue_document(other.pk,'BC',self.user)
