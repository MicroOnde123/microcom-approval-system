from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from .models import Material, MaterialReceipt, MaterialReceiptLine
from .receipt_history import receipt_history, receipt_detail, receipt_queryset, display_receipt
from .test_material_entries import Fixtures
from requests_app.models import StockMovement


class ReceiptHistoryTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("material_receipt_history")
        self.first, _ = self.receive(receipt_data={**self.data, "received_on": "2026-11-01", "supplier": "Alpha supply", "delivery_reference": "DEL-A"})
        self.second, _ = self.receive(receipt_data={**self.data, "received_on": "2026-11-03", "quantity": "3", "supplier": "Beta supply", "delivery_reference": "DEL-B"})

    def detail(self, receipt=None):
        return reverse("material_receipt_detail", args=[(receipt or self.first).pk])

    def legacy(self):
        receipt = MaterialReceipt.objects.create(operation_token=uuid4(), reference="IN-LEGACY", payload_hash="a" * 64,
            received_on="2026-10-01", supplier="Legacy supplier", delivery_reference="LEGACY-DEL", created_by=self.user)
        movement = StockMovement.objects.create(material=self.material, quantity=1, movement_type="IN", performed_by=self.user)
        MaterialReceiptLine.objects.create(receipt=receipt, material=self.material, quantity=1, stock_after=9, movement=movement)
        return receipt

    def test_listing_fields_and_each_delivery_is_independent(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Alpha supply")
        self.assertContains(response, "Beta supply")
        self.assertContains(response, "DEL-A")
        self.assertContains(response, "DEL-B")
        self.assertContains(response, "Cable")
        self.assertContains(response, "CAB")
        self.assertContains(response, self.first.reference)
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertContains(response, "Existing material")
        self.assertEqual(self.first.supplier, "Alpha supply")

    def test_search_fields_date_ranges_and_transaction_types(self):
        new_receipt, _ = self.receive(mode="new")
        legacy = self.legacy()
        for query, expected in [("Cable", 3), ("CAB", 3), (self.first.reference, 1), ("Alpha supply", 1), ("DEL-B", 1), ("nothing matches", 0), ("Bolt", 1)]:
            with self.subTest(query=query):
                response = self.client.get(self.url, {"q": query})
                self.assertEqual(response.context["page_obj"].paginator.count, expected)
        for kind, count in [("new", 1), ("existing", 2), ("unknown", 1)]:
            response = self.client.get(self.url, {"transaction_type": kind})
            self.assertEqual(response.context["page_obj"].paginator.count, count)
        response = self.client.get(self.url, {"date_from": "2026-11-01", "date_to": "2026-11-01"})
        self.assertEqual([row["receipt"].pk for row in response.context["receipt_rows"]], [self.first.pk])
        response = self.client.get(self.url, {"q": "DEL-A", "transaction_type": "existing", "date_from": "2026-11-01"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_invalid_filters_and_empty_states(self):
        for query in [{"date_from": "invalid"}, {"date_from": "2026-11-03", "date_to": "2026-11-01"}, {"transaction_type": "forged"}, {"q": "a" * 201}]:
            response = self.client.get(self.url, query)
            self.assertTrue(response.context["filter_form"].errors)
            self.assertEqual(response.context["page_obj"].paginator.count, 0)
        self.assertContains(self.client.get(self.url, {"q": "missing"}), "No receipts found")

    def test_pagination_and_return_link_preserve_filters(self):
        with patch("inventory.receipt_history.PAGE_SIZE", 1):
            response = self.client.get(self.url, {"q": "supply", "date_from": "2026-11-01", "transaction_type": "existing", "page": 2})
            self.assertEqual(len(response.context["receipt_rows"]), 1)
            self.assertEqual(response.context["page_obj"].number, 2)
            query = response.context["history_query"]
            self.assertContains(response, self.detail() + "?" + query.replace("&", "&amp;"))
            detail = self.client.get(self.detail() + "?" + query)
            self.assertEqual(detail.context["history_url"], self.url + "?" + query)
        response = self.client.get(self.detail(), {"next": "https://example.invalid", "q": "Alpha"})
        self.assertEqual(response.context["history_url"], self.url + "?q=Alpha")

    def test_snapshot_and_historical_balances_survive_catalogue_and_stock_changes(self):
        self.material.name = "Changed catalogue"
        self.material.code = "CHANGED"
        self.material.unit = "boxes"
        self.material.stock_quantity = 999
        self.material.save()
        self.category.name = "Changed category"
        self.category.save()
        response = self.client.get(self.detail())
        self.assertContains(response, "Cable")
        self.assertContains(response, "CAB")
        self.assertContains(response, "Tools")
        self.assertNotContains(response, "Changed catalogue")
        self.assertNotContains(response, "Changed category")
        item = response.context["line_rows"][0]
        self.assertEqual(item["stock_before"], 10)
        self.assertEqual(item["line"].stock_after, Decimal("12.50"))
        self.assertEqual(item["material"]["unit"], "m")
        second = self.client.get(self.detail(self.second)).context["line_rows"][0]
        self.assertEqual(second["stock_before"], Decimal("12.50"))
        self.assertEqual(second["line"].stock_after, Decimal("15.50"))
        self.assertEqual(self.client.get(self.url, {"q": "Cable"}).context["page_obj"].paginator.count, 2)
        self.assertEqual(self.client.get(self.url, {"q": "Changed catalogue"}).context["page_obj"].paginator.count, 0)

    def test_legacy_metadata_is_unknown_and_never_backfilled(self):
        receipt = self.legacy()
        before = list(MaterialReceipt.objects.values())
        lines_before = list(MaterialReceiptLine.objects.values())
        response = self.client.get(self.detail(receipt))
        self.assertContains(response, "Not recorded")
        self.assertContains(response, "Current catalogue")
        item = response.context["line_rows"][0]
        self.assertFalse(item["snapshot_recorded"])
        self.assertEqual(item["stock_before"], 8)
        self.assertEqual(item["line"].stock_after, 9)
        self.assertEqual(self.client.get(self.url, {"q": "Legacy supplier"}).context["page_obj"].paginator.count, 1)
        self.assertEqual(list(MaterialReceipt.objects.values()), before)
        self.assertEqual(list(MaterialReceiptLine.objects.values()), lines_before)

    def test_permission_checks_including_direct_urls_inactive_users_and_other_receivers(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.get(self.detail()).status_code, 302)
        for active, manager, superuser, allowed in [(True, False, False, False), (False, True, True, False), (True, True, False, True), (True, False, True, True)]:
            actor = get_user_model().objects.create_user(username=f"viewer-{active}-{manager}-{superuser}", is_active=active, can_manage_stock=manager, is_superuser=superuser)
            for view, args in [(receipt_history, ()), (receipt_detail, (self.first.pk,))]:
                request = RequestFactory().get(self.url)
                request.user = actor
                if allowed: self.assertEqual(view(request, *args).status_code, 200)
                else:
                    with self.assertRaises(PermissionDenied): view(request, *args)

    def test_read_only_routes_and_not_found(self):
        before = list(MaterialReceipt.objects.values())
        for url in (self.url, self.detail()):
            self.assertEqual(self.client.post(url, {}).status_code, 405)
            self.assertEqual(self.client.delete(url).status_code, 405)
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(url).status_code, 200)
            self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries))
        self.assertEqual(self.client.get(reverse("material_receipt_detail", args=[999999])).status_code, 404)
        self.assertEqual(list(MaterialReceipt.objects.values()), before)

    def test_prefetch_is_constant_and_multi_line_search_does_not_duplicate_receipts(self):
        extra = Material.objects.create(name="Cable extra", code="CAB-EXTRA", category=self.category)
        movement = StockMovement.objects.create(material=extra, quantity=1, movement_type="IN")
        MaterialReceiptLine.objects.create(receipt=self.first, material=extra, quantity=1, stock_after=1, movement=movement)
        with self.assertNumQueries(2):
            rows = [display_receipt(receipt) for receipt in receipt_queryset()]
            self.assertEqual(sum(len(row["line_rows"]) for row in rows), 3)
            for row in rows:
                str(row["receipt"].created_by)
                for item in row["line_rows"]: str(item["line"].movement.created_at)
        response = self.client.get(self.url, {"q": "Cable"})
        self.assertEqual(response.context["page_obj"].paginator.count, 2)

    def evidence(self, name, response):
        import os
        from pathlib import Path
        if not os.environ.get("MATERIAL_RECEIPT_UI_EVIDENCE"):
            return
        root = Path(__file__).resolve().parent.parent
        target = root / "local_artifacts" / "receipt_history_ui"
        target.mkdir(parents=True, exist_ok=True)
        text = response.content.decode().replace('"/static/', '"' + (root / "static").as_uri() + '/')
        (target / (name + ".html")).write_text(text, encoding="utf-8")

    def test_en_fr_labels_dates_and_history_navigation(self):
        legacy = self.legacy()
        for language, label in [("en", "Receipt History"), ("fr", "Historique des r\u00e9ceptions")]:
            self.client.cookies["django_language"] = language
            self.assertContains(self.client.get(reverse("material_entries")), label)
            response = self.client.get(self.url)
            self.assertContains(response, label)
            detail = self.client.get(self.detail())
            self.assertContains(detail, "2026-11-01" if language == "en" else "01/11/2026")
            self.assertContains(detail, "Alpha supply")
            self.assertContains(detail, "DEL-A")
            self.evidence(language + "-history", response)
            self.evidence(language + "-detail", detail)
            self.evidence(language + "-legacy", self.client.get(self.detail(legacy)))

    def test_metadata_capture_preserves_hash_and_legacy_retry(self):
        from .entry_services import new_token, receive_stock
        token = new_token(self.user, "existing")
        receipt, _ = self.receive(token)
        original_hash = receipt.payload_hash
        self.assertEqual(receipt.transaction_type, "existing")
        self.assertEqual(receipt.lines.get().material_snapshot["version"], 1)
        # Simulate the same receipt written before additive metadata existed.
        MaterialReceipt.objects.filter(pk=receipt.pk).update(transaction_type=None)
        receipt.lines.update(material_snapshot=None)
        with CaptureQueriesContext(connection) as queries:
            retry, created = self.receive(token)
        self.assertFalse(created)
        self.assertEqual(retry.payload_hash, original_hash)
        self.assertIsNone(retry.transaction_type)
        self.assertIsNone(retry.lines.get().material_snapshot)
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries))
        new_receipt, _ = self.receive(mode="new")
        self.assertEqual(new_receipt.transaction_type, "new")
