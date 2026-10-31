"""Synthetic operational return/reconciliation integration; isolated PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import hashlib
import tempfile

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, close_old_connections, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from django.utils.translation import override

from .test_stock_safety import StockSafetyFixtures
from .material_outcomes import issue_receipt, reconcile, OUTCOMES, quantity
from .models import (MaterialReconciliation, MaterialReconciliationLine, MaterialReconciliationReturnLink,
    ReturnReceipt, ReturnReceiptLine, ReturnReceiptSequence, ReturnReceiptArtifact, StockMovement, RequestMaterialItem)
from .return_receipt_documents import generate_receipt_pdf, read_artifact


class OutcomeFixtures(StockSafetyFixtures):
    def setUp(self):
        super().setUp()
        self.issue()

    def allocations(self, returned=0, client=0, microcom=0):
        return {self.item.pk: dict(zip(OUTCOMES, [client, microcom, 10-returned-client-microcom, returned]))}

    def reconcile(self, allocations=None, revision=0, token=None, **kwargs):
        return reconcile(self.req.pk, self.user, allocations=allocations or self.allocations(),
            expected_revision=revision, reported_by_id=self.req.submitted_by_id, reason="Technician report",
            token=token or uuid4(), **kwargs)

    def receipt(self, movements, token=None, user=None):
        return issue_receipt(self.req.pk, user or self.user, [m.pk for m in movements], token or uuid4())


class MaterialOutcomeTests(OutcomeFixtures, TestCase):
    def test_cpe_mixed_outcomes_preserve_microcom_bc_bs_and_inventory(self):
        from inventory.models import Material, Succursale
        from .material_documents import issue_document
        from .models import RequestAuditLog
        req, cpe = self.make_request(quantity=1)
        branch = Succursale.objects.create(code="CPE", name="Microcom test branch", physical_address="Test address")
        req.classification, req.succursale = "MICROCOM", branch
        req.save(update_fields=["classification", "succursale"])
        extras = []
        for code, name in (("CABLE", "Radio cable"), ("POWER", "CPE power supply")):
            material = Material.objects.create(category=self.category, code=code, name=name, unit="pcs", stock_quantity=5)
            extras.append(RequestMaterialItem.objects.create(request=req, material=material, quantity=1))
        self.issue(req)
        documents = [issue_document(req.pk, kind, self.user).reference for kind in ("BC", "BS")]
        out_ids = list(StockMovement.objects.filter(request=req, movement_type="OUT").values_list("pk", flat=True))
        returned = [self.restore(1, item=item)[0] for item in extras]
        allocations = {item.pk: {key: int(key == ("CLIENT" if item.pk == cpe.pk else "RETURNED")) for key in OUTCOMES} for item in [cpe, *extras]}
        record = reconcile(req.pk, self.user, allocations=allocations, expected_revision=0,
            reported_by_id=req.submitted_by_id, reason="Faulty client CPE replaced; unused cable and power supply returned", token=uuid4())
        receipt = issue_receipt(req.pk, self.user, [m.pk for m in returned], uuid4())
        self.assertEqual(record.lines.get(item=cpe).outcome, "CLIENT")
        self.assertEqual(receipt.lines.count(), 2)
        req.refresh_from_db()
        self.assertEqual((req.classification, req.succursale_id, req.status, req.stock_deducted), ("MICROCOM", branch.pk, "APPROVED", True))
        self.assertEqual([issue_document(req.pk, kind, self.user).reference for kind in ("BC", "BS")], documents)
        self.assertEqual(list(StockMovement.objects.filter(request=req, movement_type="OUT").values_list("pk", flat=True)), out_ids)
        for item in extras:
            item.material.refresh_from_db()
            self.assertEqual(item.material.stock_quantity, 5)
        self.assertTrue(RequestAuditLog.objects.filter(request=req, action="RECONCILIATION").exists())

    def test_outcomes_do_not_reclassify_or_change_stock(self):
        before = self.balance()
        row = self.reconcile(self.allocations(client=3, microcom=2))
        self.assertEqual(row.lines.count(), 3)
        self.assertEqual(self.balance(), before)
        self.req.refresh_from_db()
        self.assertIsNone(self.req.classification)
        self.assertEqual(StockMovement.objects.filter(movement_type="OUT").count(), 1)

    def test_preexisting_partial_returns_and_append_only_revisions(self):
        movement, _ = self.restore(2)
        first = self.reconcile(self.allocations(returned=2, client=3))
        self.restore(1)
        second = self.reconcile(self.allocations(returned=3, client=3), revision=1)
        self.assertEqual(second.previous, first)
        self.assertEqual(MaterialReconciliationReturnLink.objects.count(), 2)
        self.assertEqual(MaterialReconciliationReturnLink.objects.filter(movement=movement).count(), 1)
        self.assertEqual(first.lines.get(outcome="RETURNED").quantity, 2)
        self.assertEqual(self.balance(), 93)

    def test_exact_replay_and_conflicting_replay(self):
        token = uuid4()
        first = self.reconcile(token=token)
        self.assertEqual(self.reconcile(token=token), first)
        with self.assertRaises(ValidationError):
            self.reconcile(self.allocations(client=1), token=token)
        self.assertEqual(MaterialReconciliation.objects.count(), 1)

    def test_stale_revision_and_wrong_technician_fail(self):
        self.reconcile()
        with self.assertRaises(ValidationError):
            self.reconcile()
        with self.assertRaises(ValidationError):
            reconcile(self.req.pk, self.user, allocations=self.allocations(), expected_revision=1,
                reported_by_id=self.user.pk, reason="Report", token=uuid4())

    def test_overallocation_and_unrecorded_return_fail(self):
        for values in (self.allocations(returned=1), {self.item.pk: {"CLIENT": 11,"MICROCOM": 0,"RETAINED": 0,"RETURNED": 0}}):
            with self.assertRaises(ValidationError):
                self.reconcile(values)
        self.assertFalse(MaterialReconciliation.objects.exists())

    def test_permissions_and_cross_actor_tokens(self):
        with self.assertRaises(PermissionDenied):
            reconcile(self.req.pk, self.other, allocations=self.allocations(), expected_revision=0,
                reported_by_id=self.other.pk, reason="Report", token=uuid4())
        movement, _ = self.restore(1)
        with self.assertRaises(PermissionDenied):
            self.receipt([movement], user=self.other)
        self.other.can_manage_stock = True
        self.other.save(update_fields=["can_manage_stock"])
        token = uuid4()
        self.receipt([movement], token)
        with self.assertRaises(ValidationError):
            self.receipt([movement], token, self.other)

    def test_receipt_replay_reprint_and_duplicate_movement(self):
        movement, _ = self.restore(2)
        token = uuid4()
        receipt = self.receipt([movement], token)
        self.assertEqual(self.receipt([movement], token), receipt)
        self.assertRegex(receipt.reference, r"^RCP/0001/\d{4}$")
        with self.assertRaises(ValidationError):
            self.receipt([movement])
        self.assertEqual(ReturnReceiptSequence.objects.get().last_counter, 1)
        self.assertEqual(self.balance(), 92)

    def test_client_and_no_invoice_receipts(self):
        self.req.classification = "CLIENT"
        self.req.save(update_fields=["classification"])
        movement, _ = self.restore(1)
        receipt = self.receipt([movement])
        self.assertEqual(receipt.request, self.req)
        self.assertEqual(receipt.snapshot["lines"][0]["quantity"], "1.00")

    def test_missing_ambiguous_or_wrong_movements(self):
        out = StockMovement.objects.get(movement_type="OUT")
        with self.assertRaises(ValidationError):
            self.receipt([out])
        with self.assertRaises(ValidationError):
            issue_receipt(self.req.pk, self.user, [], uuid4())
        RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=1)
        with self.assertRaises(ValidationError):
            self.reconcile()

    def test_pdf_bilingual_integrity_and_frozen_snapshot(self):
        movement, _ = self.restore(1)
        receipt = self.receipt([movement])
        before = self.balance()
        root = Path(tempfile.mkdtemp(prefix="receipt-pdfs-", dir=Path(settings.MEDIA_ROOT).parent))
        with override_settings(INVOICE_DOCUMENT_ROOT=root):
            for language in ("en", "fr"):
                artifact = generate_receipt_pdf(receipt.pk, self.user, language)
                content = read_artifact(artifact, self.user)
                self.assertTrue(content.startswith(b"%PDF-"))
                self.assertEqual(hashlib.sha256(content).hexdigest(), artifact.checksum)
                self.assertEqual(generate_receipt_pdf(receipt.pk, self.user, language), artifact)
                with self.assertRaises(PermissionDenied):
                    read_artifact(artifact, self.other)
            self.assertEqual(receipt.artifacts.count(), 2)
            artifact = receipt.artifacts.first()
            (root / "physical-return-receipts" / artifact.file_reference).write_bytes(b"damaged")
            with self.assertRaises(ValidationError):
                read_artifact(artifact, self.user)
        self.material.name = "Edited live name"
        self.material.save(update_fields=["name"])
        receipt.refresh_from_db()
        self.assertEqual(receipt.snapshot["lines"][0]["material"], "Router")
        self.assertEqual(self.balance(), before)

    def test_quantity_validation(self):
        for value in ("NaN", "Infinity", "-.01", ".001", "100000000", "bad"):
            with self.assertRaises(ValidationError):
                quantity(value)
        self.assertEqual(quantity("0"), 0)

    def test_ui_csrf_get_cancel_permissions_and_translations(self):
        url = reverse("material_outcomes", args=[self.req.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.user)
        for language, label in (("en", "Material Management"), ("fr", "Gestion du matériel")):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            response = self.client.get(url)
            self.assertContains(response, label)
            self.assertContains(response, 'csrfmiddlewaretoken')
            self.assertContains(response, reverse("request_detail", args=[self.req.pk]))
        self.assertFalse(ReturnReceipt.objects.exists())
        self.assertFalse(MaterialReconciliation.objects.exists())
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(url, {"action": "reconcile"}).status_code, 403)

    def test_document_endpoint_requires_post_and_permission(self):
        movement, _ = self.restore(1)
        receipt = self.receipt([movement])
        url = reverse("return_receipt_pdf", args=[receipt.pk])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 403)


class MaterialOutcomeConcurrencyTests(OutcomeFixtures, TransactionTestCase):
    def race(self, fn):
        barrier = Barrier(2)
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return fn().pk
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: run(), range(2)))

    def test_concurrent_receipt_exact_replay(self):
        movement, _ = self.restore(1)
        token = uuid4()
        result = self.race(lambda: self.receipt([movement], token))
        self.assertEqual(result[0], result[1])
        self.assertEqual(ReturnReceiptSequence.objects.get().last_counter, 1)
        self.assertEqual(ReturnReceiptLine.objects.count(), 1)
        self.assertEqual(self.balance(), 91)

    def test_concurrent_reconciliation_exact_replay(self):
        token = uuid4()
        result = self.race(lambda: self.reconcile(token=token))
        self.assertEqual(result[0], result[1])
        self.assertEqual(MaterialReconciliation.objects.count(), 1)

    def test_immutability_source_and_late_append_guards(self):
        movement, _ = self.restore(1)
        receipt = self.receipt([movement])
        reconciliation = self.reconcile(self.allocations(returned=1))
        for model, pk, field, value in ((ReturnReceipt, receipt.pk, "reference", "changed"),
                (MaterialReconciliation, reconciliation.pk, "reason", "changed"),
                (StockMovement, movement.pk, "quantity", 2)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.filter(pk=pk).update(**{field: value})
        with self.assertRaises(IntegrityError), transaction.atomic():
            MaterialReconciliationLine.objects.create(reconciliation=reconciliation, item=self.item,
                outcome="CLIENT", quantity=1, snapshot={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReturnReceiptSequence.objects.update(last_counter=0)

    def test_receipt_failure_rolls_back_number_and_audit(self):
        from unittest.mock import patch
        movement, _ = self.restore(1)
        with patch("requests_app.material_outcomes.RequestAuditLog.objects.create", side_effect=ValidationError("Synthetic")):
            with self.assertRaises(ValidationError):
                self.receipt([movement])
        self.assertFalse(ReturnReceipt.objects.exists())
        self.assertFalse(ReturnReceiptSequence.objects.exists())
        self.assertEqual(self.balance(), 91)

    def test_year_boundary_uses_database_kinshasa_and_counters_beyond_9999(self):
        def at(instant):
            def wrapper(execute, sql, params, many, context):
                if 'INSERT INTO requests_app_returnreceiptsequence' in sql:
                    sql = sql.replace('clock_timestamp()', f"TIMESTAMPTZ '{instant}'")
                return execute(sql, params, many, context)
            return wrapper
        first, _ = self.restore(1)
        second, _ = self.restore(1)
        with connection.execute_wrapper(at('2026-12-31 22:59:59+00')):
            old = self.receipt([first])
        with connection.execute_wrapper(at('2026-12-31 23:00:00+00')):
            new = self.receipt([second])
        self.assertEqual((old.reference, new.reference), ("RCP/0001/2026", "RCP/0001/2027"))
        ReturnReceiptSequence.objects.create(year=2028, last_counter=9999)
        third, _ = self.restore(1)
        with connection.execute_wrapper(at('2028-01-01 00:00:00+00')):
            large = self.receipt([third])
        self.assertEqual(large.reference, "RCP/10000/2028")

    def test_used_migration_reversal_fails_closed(self):
        from importlib import import_module
        from django.apps import apps
        from django.db.migrations.exceptions import IrreversibleError
        module = import_module('requests_app.migrations.0020_material_reconciliation_return_receipts')
        self.reconcile()
        with self.assertRaises(IrreversibleError), transaction.atomic():
            with connection.schema_editor(atomic=False) as editor:
                module.unused_reversal(apps, editor)
        self.assertEqual(MaterialReconciliation.objects.count(), 1)
