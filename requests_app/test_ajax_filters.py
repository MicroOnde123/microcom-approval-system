"""Full-HTML AJAX contracts; financial/stock behavior stays in existing services."""
from datetime import date
from django.test import TestCase
import re
from django.urls import reverse
from invoicing.test_lifecycle import LifecycleFixtures


class AjaxFilteringTests(LifecycleFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.user.can_manage_stock=True
        self.user.can_view_administration_reports=True
        self.user.save(update_fields=['can_manage_stock','can_view_administration_reports'])
        self.client.force_login(self.user)

    def test_all_six_routes_return_single_results_and_shared_script_in_both_languages(self):
        for name in ['my_requests','pending_approvals','approval_history','administration_reports','material_reports','invoicing:list']:
            for language in ['en','fr']:
                with self.subTest(name=name,language=language):
                    response=self.client.get(reverse(name),{'q':'no-results'},HTTP_X_REQUESTED_WITH='XMLHttpRequest',HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.status_code,200)
                    self.assertContains(response,'id="live-filter-results"',count=1)
                    self.assertContains(response,'js/auto_filters.js',count=1)
                    self.assertEqual(len(re.findall(r'<form\b[^>]*\bdata-auto-filters="true"',response.content.decode())),1)
                    self.assertContains(response,'data-error-label=')
                    self.assertContains(response,'Recherche en cours' if language=='fr' else 'Searching...')
                    if language=='fr':
                        self.assertContains(response,'Résultats actualisés.')
                        self.assertContains(response,'Vérifiez les erreurs des filtres.')

    def test_ajax_header_does_not_bypass_existing_permissions(self):
        self.client.force_login(self.other)
        for name in ['material_reports','administration_reports','invoicing:list']:
            self.assertEqual(self.client.get(reverse(name),HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)

    def test_invoice_print_filters_and_material_export_urls_match_active_filters(self):
        filters={'q':'unique phrase','date_from':'2026-10-01','date_to':'2026-10-31','status':'FINALIZED'}
        response=self.client.get(reverse('invoicing:list'),filters,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.context['active_filters'],filters)
        self.assertContains(response,'name="date_from" value="2026-10-01"')
        self.assertContains(response,'id="invoice-bulk-print-form" data-filter-dependent')
        response=self.client.get(reverse('material_reports'),{'q':'unique phrase','date_from':'2026-10-01'},HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(response,'q=unique+phrase')
        self.assertContains(response,'date_from=2026-10-01')
        self.assertContains(response,'id="material-bulk-print-form" data-filter-dependent')
        self.assertContains(response,'material-export-csv')
        self.assertContains(response,'material-export-excel')

    def test_malformed_queue_and_material_filters_fail_closed_bilingually(self):
        for name in ['pending_approvals','material_reports']:
            for filters in [{'date_from':'not-a-date'},{'department':'not-an-id'},
                            {'date_from':'2026-10-30','date_to':'2026-10-01'}]:
                for language in ['en','fr']:
                    response=self.client.get(reverse(name),filters,HTTP_X_REQUESTED_WITH='XMLHttpRequest',HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.status_code,200)
                    self.assertTrue(response.context['filter_validation_errors'])
                    self.assertContains(response,'role="alert"')
                    self.assertEqual(len(response.context['approvals' if name=='pending_approvals' else 'requests']),0)

    def test_valid_queue_and_material_dates_keep_authorized_results(self):
        pending,_=self.make_request(1)
        pending.date_needed=date(2026,10,15);pending.save(update_fields=['date_needed'])
        self.req.date_needed=date(2026,10,15);self.req.save(update_fields=['date_needed'])
        filters={'date_from':'2026-10-01','date_to':'2026-10-31'}
        for name in ['pending_approvals','material_reports']:
            response=self.client.get(reverse(name),filters,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.context['filter_validation_errors'])
            if name=='pending_approvals':
                self.assertIn(pending.pk,[row.request_id for row in response.context['approvals']])
                self.assertContains(response,self.department.name)
                self.assertNotContains(response,'department.name }}')
                self.assertContains(response,'for="pending-filter-department"')
            else:
                self.assertIn(self.req.pk,[row.pk for row in response.context['requests']])
        self.client.force_login(self.other)
        response=self.client.get(reverse('pending_approvals'),filters,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(len(response.context['approvals']),0)
        self.assertEqual(self.client.get(reverse('material_reports'),filters,HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)

    def test_invalid_filters_never_bypass_authentication_or_stock_permission(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('material_reports'),{'date_from':'bad'},HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,403)
        self.client.logout()
        for name in ['pending_approvals','material_reports']:
            self.assertEqual(self.client.get(reverse(name),{'date_from':'bad'},HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,302)
