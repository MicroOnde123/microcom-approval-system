"""Read-only reporting of synthetic historical discrepancies, never repairs."""
import json
from io import StringIO
from decimal import Decimal
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from .test_stock_safety import StockSafetyFixtures
from .models import RequestMaterialItem, StockMovement, RequestAuditLog
from .stock_services import material_return_totals
from .stock_integrity import annotate_return_ledgers, movement_prefetch


class StockIntegrityReportTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.issue()
        self.client.force_login(self.user)

    def report(self, req=None, language="en"):
        self.client.cookies['django_language'] = language
        return self.client.get(reverse('material_reports'), {'q': (req or self.req).request_number})

    def ledger(self, response):
        return response.context['requests'][0].material_items.all()[0].return_ledger

    def test_partial_return_has_all_quantities_and_active_action(self):
        self.restore(3)
        response = self.report()
        self.assertEqual(self.ledger(response)['issued_quantity'], 10)
        self.assertEqual(self.ledger(response)['returned_quantity'], 3)
        self.assertEqual(self.ledger(response)['remaining_quantity'], 7)
        self.assertContains(response, 'Returnable')
        self.assertContains(response, reverse('return_material_to_stock', args=[self.item.pk]))
        self.assertContains(response, 'Movement history')

    def test_fully_returned_has_no_active_return_action(self):
        self.restore(10)
        response = self.report()
        self.assertEqual(self.ledger(response)['remaining_quantity'], 0)
        self.assertContains(response, 'Fully returned')
        self.assertNotContains(response, reverse('return_material_to_stock', args=[self.item.pk]))
        self.assertContains(response, reverse('request_detail', args=[self.req.pk]))

    def test_historical_15_issued_20_returned_fails_closed_and_is_bilingual(self):
        req, item = self.make_request(quantity=15)
        self.issue(req)
        for _ in range(2):
            StockMovement.objects.create(request=req, material=self.material, movement_type='RETURN', quantity=10)
        balance = self.balance()
        for language, warning in (('en','Historical stock discrepancy — review required.'), ('fr','Incohérence historique du stock — vérification nécessaire.')):
            response = self.report(req, language)
            ledger = self.ledger(response)
            self.assertEqual((ledger['issued_quantity'], ledger['returned_quantity'], ledger['remaining_quantity']), (15,20,None))
            self.assertEqual(ledger['issues'], ['over_return'])
            self.assertContains(response, warning)
            self.assertNotContains(response, reverse('return_material_to_stock', args=[item.pk]))
            self.assertContains(response, reverse('request_detail', args=[req.pk]))
        with self.assertRaises(ValidationError):
            material_return_totals(item)
        self.assertEqual(self.balance(), balance)

    def test_missing_and_mismatched_out_movements(self):
        movement = StockMovement.objects.get(request=self.req, movement_type='OUT')
        StockMovement.objects.filter(pk=movement.pk).update(quantity=9)
        response = self.report()
        self.assertIn('issue_quantity_mismatch', self.ledger(response)['issues'])
        self.assertNotContains(response, reverse('return_material_to_stock', args=[self.item.pk]))
        StockMovement.objects.filter(pk=movement.pk).delete()
        response = self.report()
        self.assertIsNone(self.ledger(response)['issued_quantity'])
        self.assertContains(response, 'Not recorded')
        self.assertIn('missing_positive_out', self.ledger(response)['issues'])

    def test_nonpositive_and_ambiguous_history(self):
        StockMovement.objects.create(request=self.req, material=self.material, movement_type='RETURN', quantity=0)
        RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=1)
        response = self.report()
        self.assertIn('nonpositive_movement', self.ledger(response)['issues'])
        self.assertIn('ambiguous_material_lines', self.ledger(response)['issues'])
        self.assertNotContains(response, reverse('return_material_to_stock', args=[self.item.pk]))

    def test_multiple_out_rows_are_not_mislabeled_when_existing_rules_allow_them(self):
        StockMovement.objects.filter(request=self.req, movement_type='OUT').update(quantity=5)
        StockMovement.objects.create(request=self.req, material=self.material, movement_type='OUT', quantity=5)
        self.assertTrue(self.ledger(self.report())['consistent'])
        self.assertEqual(material_return_totals(self.item)['remaining_quantity'], 10)

    def test_unauthorized_users_cannot_see_history(self):
        self.client.force_login(self.other)
        response = self.report()
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, self.req.request_number, status_code=403)
        self.assertNotContains(response, 'Movement history', status_code=403)

    def test_report_is_read_only_and_ledger_annotation_has_no_n_plus_one(self):
        from .models import Request
        reqs = list(Request.objects.filter(pk=self.req.pk).prefetch_related('material_items', movement_prefetch()))
        with self.assertNumQueries(0):
            annotate_return_ledgers(reqs)
        before = (self.balance(), StockMovement.objects.count(), RequestAuditLog.objects.count())
        with CaptureQueriesContext(connection) as queries:
            self.report()
        for query in queries:
            sql = query['sql'].lstrip().upper()
            self.assertFalse(sql.startswith(('INSERT','DELETE')))
            if sql.startswith('UPDATE'):
                self.assertIn('DJANGO_SESSION', sql)
        self.assertEqual((self.balance(), StockMovement.objects.count(), RequestAuditLog.objects.count()), before)


class StockIntegrityCommandTests(StockSafetyFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.issue()

    def audit(self, **options):
        output = StringIO()
        call_command('audit_stock_integrity', confirm_database=connection.settings_dict['NAME'], stdout=output, **options)
        return json.loads(output.getvalue())

    def test_command_runs_read_only_repeatable_read_and_ends_in_rollback(self):
        StockMovement.objects.create(request=self.req, material=self.material, movement_type='RETURN', quantity=11)
        before = (self.balance(), StockMovement.objects.count(), RequestAuditLog.objects.count())
        with CaptureQueriesContext(connection) as queries:
            result = self.audit(language='fr')
        self.assertEqual(result['issue_counts'], {'over_return':1})
        self.assertEqual(result['message'], 'Incohérence historique du stock — vérification nécessaire.')
        self.assertEqual(result['details'], [])
        self.assertFalse(result['repairs_performed'])
        sql = [q['sql'].upper() for q in queries]
        self.assertTrue(any('REPEATABLE READ READ ONLY' in q for q in sql))
        self.assertIn('ROLLBACK', sql)
        self.assertFalse(any(q.lstrip().startswith(('INSERT','UPDATE','DELETE','ALTER','CREATE','DROP')) for q in sql))
        self.assertEqual((self.balance(), StockMovement.objects.count(), RequestAuditLog.objects.count()), before)
        self.assertTrue(connection.get_autocommit())

    def test_report_redacts_text_and_bounds_optional_ids(self):
        self.user.username = 'PRIVATE_EMPLOYEE_IDENTIFIER'
        self.user.save(update_fields=['username'])
        StockMovement.objects.create(request=self.req, material=self.material, movement_type='RETURN', quantity=11,
            return_reason='CONFIDENTIAL REASON', note='CONFIDENTIAL NOTE')
        result = self.audit(include_record_ids=True, max_details=1)
        self.assertEqual(len(result['details']), 1)
        serialized = json.dumps(result)
        for private in ('CONFIDENTIAL', self.req.request_number, self.material.name, self.user.username):
            self.assertNotIn(private, serialized)
        self.assertEqual(result['details'][0]['request_id'], self.req.pk)

    def test_missing_out_ambiguous_and_orphan_movements_are_reported(self):
        StockMovement.objects.filter(request=self.req, movement_type='OUT').delete()
        RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=1)
        StockMovement.objects.create(material=self.material, movement_type='OUT', quantity=1)
        result = self.audit()
        self.assertEqual(result['issue_counts']['missing_positive_out'], 1)
        self.assertEqual(result['issue_counts']['ambiguous_material_lines'], 1)
        self.assertEqual(result['issue_counts']['unassociated_movement'], 1)

    def test_wrong_target_and_nested_transaction_fail_before_inspection(self):
        with self.assertRaises(CommandError):
            call_command('audit_stock_integrity', confirm_database='NOT_THE_TARGET', stdout=StringIO())
        with transaction.atomic(), self.assertRaises(CommandError):
            self.audit()

    def test_clean_history_and_request_scope(self):
        result = self.audit(request_id=self.req.pk)
        self.assertEqual(result['material_groups_scanned'], 1)
        self.assertEqual(result['issue_counts'], {})
        self.assertEqual(result['message'], 'No stock integrity discrepancies found.')
