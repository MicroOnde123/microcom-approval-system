"""Synthetic schema transitions only. No return-note lifecycle services."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.utils.translation import override

from requests_app.models import StockMovement
from requests_app.services import approve_step
from .configuration import business_date
from .models import (MaterialReturnNote, MaterialReturnNoteLine, MaterialReturnNoteAudit,
                     MaterialReturnNoteArtifact, DocumentSequence)
from .services import database_now
from .test_credit_guards import CreditGuardFixtures


class ReturnNoteFixtures(CreditGuardFixtures):
    def partial_history(self, price="0.0050", pre_return=0):
        self.req,self.item=self.make_request(3)
        approve_step(self.req.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
        self.req.refresh_from_db()
        if pre_return:self.excluded,_=self.restore(pre_return)
        invoice=self.create();self.price(invoice,price);self.verified_sequence()
        self.invoice=self.finalize(invoice);self.issue_allocation=self.invoice.lines.get().issue_allocation
        self.returned,_=self.restore(1)
        return self.returned

    def return_sequence(self):
        sequence=DocumentSequence.objects.filter(document_type="RETURN_NOTE").first()
        if not sequence:
            sequence=DocumentSequence.objects.create(document_type="RETURN_NOTE",year=business_date(database_now(),"Africa/Kinshasa").year,
                number_format="BR/{number:04d}/{year}",starting_value=7,next_counter=7)
            sequence.attest(self.admin,"Synthetic verified BR numbering starts at seven")
        return sequence

    def note_rows(self, movements=None, amounts=None, token=None, line_changes=None, header_changes=None):
        """Caller owns atomic boundary; manually supplies synthetic schema data."""
        movements=movements or [self.returned]
        line=self.invoice.lines.get()
        op=MaterialReturnNoteAudit.objects.create(invoice=self.invoice,actor=self.user,reason="Synthetic schema proof",
            payload={"issuance_token":str(token)} if token else {})
        note=MaterialReturnNote.objects.create(invoice=self.invoice,operation=op,currency=self.invoice.currency,
            created_by=self.user,issuance_operation_token=token)
        prior=MaterialReturnNoteLine.objects.filter(issue_allocation=self.issue_allocation).exclude(note=note)
        q=sum((a.quantity for a in prior),Decimal(0)); value=sum((a.line_total for a in prior),Decimal(0))
        for index,movement in enumerate(movements):
            q+=movement.quantity
            # Explicit HALF_UP: Decimal's ambient default is HALF_EVEN.
            from decimal import ROUND_HALF_UP
            expected=min(line.line_total,(q*line.unit_price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))-value
            fields=dict(note=note,issue_allocation=self.issue_allocation,return_movement=movement,quantity=movement.quantity,
                unit_price_snapshot=line.unit_price,line_total=amounts[index] if amounts else expected,
                description_snapshot=line.description_snapshot,material_code_snapshot=line.material_code_snapshot,unit_snapshot=line.unit_snapshot)
            fields.update(line_changes or {})
            MaterialReturnNoteLine.objects.create(**fields)
            value+=fields['line_total']
        note.refresh_from_db()
        note.company_snapshot=self.invoice.company_snapshot; note.succursale_snapshot=self.invoice.succursale_snapshot
        note.branding_snapshot=self.invoice.branding_snapshot; note.request_reference_snapshot=self.invoice.request_reference_snapshot
        note.original_invoice_snapshot={"version":1,"number":self.invoice.number,"issue_date":self.invoice.issue_date.isoformat(),
            "total":str(self.invoice.total),"currency":self.invoice.currency,"request_reference":self.invoice.request_reference_snapshot,
            "snapshot_version":self.invoice.snapshot_version,"rounding_policy":self.invoice.rounding_policy}
        note.rounding_policy="RETURN_CUMULATIVE_HALF_UP_2_V1"
        note.total=sum((a.line_total for a in note.lines.all()),Decimal(0))
        note.cumulative_returned_value=sum((n.total for n in MaterialReturnNote.objects.filter(invoice=self.invoice,status="FINALIZED")),Decimal(0))+note.total
        note.adjusted_net_value=self.invoice.total-note.cumulative_returned_value
        note.status="FINALIZED";note.sequence=self.return_sequence();note.sequence_counter=note.pk+7
        note.number=f"SYNTHETIC-BR-{note.pk}"
        note.finalized_by=self.user;note.finalized_at=database_now();note.issue_date=business_date(note.finalized_at,"Africa/Kinshasa")
        note.amount_words_fr="Valeur synthÃ©tique"
        for name,val in (header_changes or {}).items():setattr(note,name,val)
        note.save();note.refresh_from_db()
        return note


class ReturnNoteGuardTests(ReturnNoteFixtures):
    def test_multiple_movements_and_partial_notes_round_to_original_cap(self):
        first=self.partial_history();second,_=self.restore(1);third,_=self.restore(1)
        with transaction.atomic():a=self.note_rows([first,second])
        self.assertEqual(list(a.lines.order_by('pk').values_list('line_total',flat=True)),[Decimal('.01'),Decimal('0')])
        with transaction.atomic():b=self.note_rows([third])
        self.assertEqual(b.total,Decimal('.01'));self.assertEqual(b.cumulative_returned_value,self.invoice.total)
        self.assertEqual(b.adjusted_net_value,0)

    def test_preinvoice_exclusions_are_not_valued_twice(self):
        self.partial_history(price='2',pre_return=1)
        with self.assertRaises(IntegrityError),transaction.atomic():self.note_rows([self.excluded])
        with transaction.atomic():note=self.note_rows()
        self.assertEqual(note.total,Decimal('2'));self.assertEqual(note.adjusted_net_value,Decimal('2'))

    def test_invalid_source_histories_are_blocked_without_repair(self):
        self.setup_invoice()
        from requests_app.models import RequestMaterialItem
        mutations=[('UPDATE requests_app_stockmovement SET quantity=0 WHERE id=%s',[self.out.pk]),
                   ('UPDATE requests_app_stockmovement SET movement_type=\'IN\' WHERE id=%s',[self.returned.pk]),
                   ('UPDATE requests_app_stockmovement SET quantity=4 WHERE id=%s',[self.returned.pk])]
        for sql,params in mutations:
            with self.subTest(sql=sql),self.assertRaises((IntegrityError,ValidationError)),transaction.atomic():
                with connection.cursor() as c:c.execute(sql,params)
                self.returned.refresh_from_db();self.note_rows()
        self.returned.refresh_from_db()
        with self.assertRaises(IntegrityError),transaction.atomic():
            RequestMaterialItem.objects.create(request=self.req,material=self.material,quantity=1)
            self.note_rows()

    def test_original_frozen_prices_survive_catalogue_changes(self):
        self.setup_invoice(price='2')
        self.material.unit_price=Decimal('100');self.material.currency='USD';self.material.save(update_fields=['unit_price','currency'])
        with transaction.atomic():note=self.note_rows()
        self.assertEqual(note.lines.get().unit_price_snapshot,Decimal('2'))
        self.assertEqual(note.total,Decimal('6'))

    def test_finalized_credit_blocks_return_note(self):
        self.setup_invoice();credit=self.new_credit();self.reserve(credit)
        self.review(credit)
        with self.write('FINALIZE'):self.schema_transition(credit)
        with self.assertRaises(IntegrityError),transaction.atomic():self.note_rows()

    def test_released_credit_evidence_is_preserved_but_does_not_reserve(self):
        self.setup_invoice();credit=self.new_credit();allocation=self.reserve(credit)
        with self.write('RELEASE') as op:
            allocation.released_at=database_now();allocation.release_operation=op;allocation.save()
        with transaction.atomic():self.note_rows()
        allocation.refresh_from_db();self.assertIsNotNone(allocation.released_at)
        self.assertEqual(allocation.quantity,1)

    def test_stock_returns_continue_after_note_and_credit_reservation(self):
        self.partial_history(price='2')
        with transaction.atomic():self.note_rows()
        movement,_=self.restore(1)
        self.assertEqual(movement.quantity,1)
        self.assertEqual(MaterialReturnNoteLine.objects.count(),1)

    def test_numbering_isolation_reference_collision_and_sequence_freeze(self):
        self.setup_invoice();before=list(DocumentSequence.objects.filter(document_type='INVOICE').values())
        with self.assertRaises(IntegrityError),transaction.atomic():self.note_rows(header_changes={'number':self.invoice.number})
        with self.assertRaises(IntegrityError),transaction.atomic():
            self.note_rows(header_changes={'sequence':DocumentSequence.objects.get(document_type='INVOICE')})
        with transaction.atomic():note=self.note_rows()
        sequence=note.sequence;sequence.number_format='OTHER/{number}/{year}'
        with self.assertRaises(IntegrityError),transaction.atomic():sequence.save()
        self.assertEqual(list(DocumentSequence.objects.filter(document_type='INVOICE').values()),before)

    def test_return_note_operations_reject_nonfinal_invoice_and_replay(self):
        invoice=self.create()
        with self.assertRaises(IntegrityError),transaction.atomic():
            MaterialReturnNoteAudit.objects.create(invoice=invoice,actor=self.user,reason='Not final')
        self.setup_invoice()
        with transaction.atomic():op=MaterialReturnNoteAudit.objects.create(invoice=self.invoice,actor=self.user,reason='No document yet')
        with self.assertRaises(IntegrityError),transaction.atomic():
            MaterialReturnNote.objects.create(invoice=self.invoice,operation=op,currency='USD',created_by=self.user)

    def test_whole_return_frozen_snapshots_and_no_stock_changes(self):
        self.setup_invoice();before=self.source_snapshot()
        with transaction.atomic():note=self.note_rows(token=uuid4())
        self.assertEqual(note.total,Decimal('.02'));self.assertEqual(note.adjusted_net_value,0)
        self.assertEqual(note.request_reference_snapshot,self.invoice.request_reference_snapshot)
        self.assertEqual(self.source_snapshot(),before)
        self.assertEqual(note.lines.get().quantity,self.returned.quantity)

    def test_incomplete_construction_cannot_commit(self):
        self.setup_invoice()
        with self.assertRaises(IntegrityError),transaction.atomic():
            op=MaterialReturnNoteAudit.objects.create(invoice=self.invoice,actor=self.user,reason="Incomplete")
            MaterialReturnNote.objects.create(invoice=self.invoice,operation=op,currency="USD",created_by=self.user)
        self.assertEqual(MaterialReturnNoteAudit.objects.count(),0)

    def test_invalid_currency_snapshots_quantities_prices_and_totals_rollback(self):
        self.setup_invoice();before=self.source_snapshot()
        cases=[({},dict(currency="EUR")),({},dict(request_reference_snapshot="forged")),
               ({'quantity':Decimal('1')},{}),({'unit_price_snapshot':Decimal('3')},{}),
               ({'unit_snapshot':'forged'},{}),({'line_total':Decimal('.01')},{}),
               ({},dict(cumulative_returned_value=Decimal('.01'))),({},dict(adjusted_net_value=Decimal('2')))]
        for line,header in cases:
            with self.subTest(line=line,header=header),self.assertRaises((IntegrityError,ValidationError)),transaction.atomic():
                self.note_rows(line_changes=line,header_changes=header)
            self.assertEqual(MaterialReturnNote.objects.count(),0)
            self.assertEqual(MaterialReturnNoteAudit.objects.count(),0)
        self.assertEqual(self.source_snapshot(),before)

    def test_duplicate_return_and_token_are_rejected(self):
        self.setup_invoice();token=uuid4()
        with transaction.atomic():self.note_rows(token=token)
        for other in (None,token):
            with self.assertRaises((IntegrityError,ValidationError)),transaction.atomic():self.note_rows(token=other)
        self.assertEqual(MaterialReturnNote.objects.count(),1)

    def test_token_uniqueness_across_distinct_returns_and_nullable_tokens(self):
        first=self.partial_history(price='2');second,_=self.restore(1);third,_=self.restore(1)
        token=uuid4()
        with transaction.atomic():self.note_rows([first],token=token)
        with self.assertRaises((IntegrityError,ValidationError)),transaction.atomic():self.note_rows([second],token=token)
        with transaction.atomic():a=self.note_rows([second])
        with transaction.atomic():b=self.note_rows([third])
        self.assertIsNone(a.issuance_operation_token);self.assertIsNone(b.issuance_operation_token)

    def test_positive_zero_value_return_note_is_valid(self):
        self.setup_invoice(price='0')
        with transaction.atomic():note=self.note_rows()
        self.assertEqual(note.total,0);self.assertGreater(note.lines.get().quantity,0)

    def test_two_concurrent_return_notes_serialize_cumulative_values(self):
        first=self.partial_history();second,_=self.restore(1);started=Event()
        def contender():
            close_old_connections()
            try:
                started.set()
                with transaction.atomic():return self.note_rows([second]).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                a=self.note_rows([first]);future=pool.submit(contender);self.assertTrue(started.wait(3))
                from concurrent.futures import TimeoutError
                with self.assertRaises(TimeoutError):future.result(.15)
            b=MaterialReturnNote.objects.get(pk=future.result(10))
        self.assertEqual((a.total,b.total),(Decimal('.01'),Decimal('0')))
        self.assertEqual(b.cumulative_returned_value,Decimal('.01'))

    def test_issued_note_lines_audit_artifacts_are_immutable(self):
        self.setup_invoice()
        with transaction.atomic():note=self.note_rows()
        artifact=MaterialReturnNoteArtifact.objects.create(note=note,language="fr",rendering_version="schema-only",
            file_reference="synthetic-not-a-file.pdf",checksum="a"*64,rendering_status="READY",created_by=self.user)
        for table,key in [('invoicing_materialreturnnote',note.pk),('invoicing_materialreturnnoteline',note.lines.get().pk),
                          ('invoicing_materialreturnnoteaudit',str(note.operation_id)),('invoicing_materialreturnnoteartifact',artifact.pk)]:
            for statement in (f'DELETE FROM {table} WHERE id=%s',f'UPDATE {table} SET id=id WHERE id=%s'):
                with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c:c.execute(statement,[key])
        with self.assertRaises(ValidationError):note.save()
        with self.assertRaises(ValidationError):artifact.save()

    def test_credit_reservation_blocks_return_notes_on_distinct_movement(self):
        first=self.partial_history(price='2');second,_=self.restore(1)
        credit=self.new_credit();self.reserve(credit,amount='2',returned=first)
        with self.assertRaises(IntegrityError),transaction.atomic():self.note_rows([second])
        self.assertFalse(MaterialReturnNoteAudit.objects.exists())
        movement,_=self.restore(1)
        self.assertEqual(movement.quantity,1)

    def test_return_note_blocks_new_credit_reservations(self):
        first=self.partial_history(price='2');second,_=self.restore(1);credit=self.new_credit()
        with transaction.atomic():self.note_rows()
        with self.assertRaises(IntegrityError):self.reserve(credit,amount='2',returned=second)
        self.assertFalse(credit.allocations.exists())

    def test_business_year_backdating_and_sequence_verification(self):
        self.setup_invoice()
        from datetime import timedelta
        for changes in ({'finalized_at':database_now()-timedelta(days=1)},
                        {'issue_date':business_date(database_now(),"Africa/Kinshasa")-timedelta(days=1)}):
            with self.subTest(changes=changes),self.assertRaises(IntegrityError),transaction.atomic():self.note_rows(header_changes=changes)
        sequence=DocumentSequence.objects.create(document_type='RETURN_NOTE',series='UNVERIFIED',year=business_date(database_now(),"Africa/Kinshasa").year,
            number_format='BR/{number:04d}/{year}')
        with self.assertRaises(IntegrityError),transaction.atomic():self.note_rows(header_changes={'sequence':sequence})

    def test_unsupported_isolation_is_rejected(self):
        self.setup_invoice()
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c:c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            MaterialReturnNoteAudit.objects.create(invoice=self.invoice,actor=self.user,reason='Unsupported isolation')

    def test_same_transaction_cross_ledger_conflict_rolls_back(self):
        self.setup_invoice();credit=self.new_credit()
        with self.assertRaises(IntegrityError),transaction.atomic():
            self.note_rows()
            self.credit_operation_fixture(self.invoice,"RESERVE")
            self.allocation_row(credit)
        self.assertFalse(MaterialReturnNote.objects.exists())

    def test_concurrent_cross_ledger_both_directions(self):
        self.setup_invoice();credit=self.new_credit()
        started=Event()
        def contender():
            close_old_connections()
            try:
                started.set()
                self.reserve(credit)
                return 'committed'
            except IntegrityError:return 'blocked'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                self.note_rows();future=pool.submit(contender);self.assertTrue(started.wait(3))
                from concurrent.futures import TimeoutError
                with self.assertRaises(TimeoutError):future.result(.15)
            self.assertEqual(future.result(10),'blocked')

    def test_concurrent_credit_winner_blocks_return_note(self):
        self.setup_invoice();credit=self.new_credit();started=Event()
        def contender():
            close_old_connections()
            try:
                started.set()
                with transaction.atomic():self.note_rows()
                return 'committed'
            except IntegrityError:return 'blocked'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.write("RESERVE"):
                self.allocation_row(credit);future=pool.submit(contender);self.assertTrue(started.wait(3))
                from concurrent.futures import TimeoutError
                with self.assertRaises(TimeoutError):future.result(.15)
            self.assertEqual(future.result(10),'blocked')

    def test_permissions_bilingual_labels_and_validation(self):
        expected={'en':'Material return note','fr':'Bon de retour'}
        for language,label in expected.items():
            with override(language):
                self.assertEqual(str(MaterialReturnNote._meta.verbose_name),label)
                audit=MaterialReturnNoteAudit(reason='')
                with self.assertRaises(ValidationError) as error:audit.clean()
                self.assertIn('motif' if language=='fr' else 'reason',str(error.exception))
        for permission in ('add_materialreturnnote','view_materialreturnnote','issue_materialreturnnote','view_materialreturnnote_document'):
            self.assertTrue(Permission.objects.filter(codename=permission,content_type__app_label='invoicing').exists())
            self.assertFalse(self.user.has_perm('invoicing.'+permission))
