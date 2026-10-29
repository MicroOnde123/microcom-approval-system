"""Synthetic legacy compatibility tests; never use production fixtures.

Only synthetic fixtures are used, including deliberately invalid legacy rows.
"""
from decimal import Decimal
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection, connections, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.translation import override
from openpyxl import load_workbook

from inventory.models import Material
from .admin import RequestMaterialItemInline
from .forms import RequestMaterialItemForm
from .models import Request, RequestMaterialItem, StockMovement
from .stock_services import material_return_totals
from .test_stock_safety import StockSafetyFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LegacyStockCompatibilityTests(StockSafetyFixtures, TestCase):
    def legacy_zero(self):
        # Bypass today's save validation solely to represent pre-0015 data.
        RequestMaterialItem.objects.filter(pk=self.item.pk).update(quantity=0)
        self.item.refresh_from_db()

    def history(self, returned):
        self.issue()
        for quantity in returned:
            StockMovement.objects.create(request=self.req, material=self.material,
                                         movement_type="RETURN", quantity=quantity)
        Material.objects.filter(pk=self.material.pk).update(stock_quantity=90 + sum(returned))
        self.req.refresh_from_db()
        self.assertFalse(self.req.stock_returned)
        self.assertIsNone(self.req.stock_returned_at)

    def snapshot(self):
        return (list(Material.objects.order_by("pk").values_list("pk", "stock_quantity")),
                list(StockMovement.objects.order_by("pk").values_list(
                    "pk", "quantity", "movement_type", "return_operation_token")))

    def test_legacy_note_save_preserves_zero_and_movement(self):
        self.issue()
        self.legacy_zero()
        StockMovement.objects.filter(request=self.req).update(quantity=0)
        before = self.snapshot()
        for fields in (None, ["note"]):
            self.item.note = "Unrelated note " + str(fields)
            with CaptureQueriesContext(connection) as queries:
                self.item.save(update_fields=fields)
            updates = [q["sql"] for q in queries if q["sql"].startswith("UPDATE")]
            self.assertEqual(len(updates), 1)
            self.assertNotIn('"quantity"', updates[0])
            self.item.refresh_from_db()
            self.assertEqual(self.item.note, "Unrelated note " + str(fields))
            self.assertEqual(self.item.quantity, 0)
            self.assertEqual(self.snapshot(), before)

    def test_admin_inline_allows_note_only_edit_and_ignores_quantity_tampering(self):
        self.legacy_zero()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        request = RequestFactory().get("/admin/")
        request.user = self.user
        inline = RequestMaterialItemInline(Request, admin.site)
        formset_class = inline.get_formset(request, self.req)
        prefix = formset_class.get_default_prefix()
        data = {f"{prefix}-TOTAL_FORMS": "1", f"{prefix}-INITIAL_FORMS": "1",
                f"{prefix}-0-id": self.item.pk, f"{prefix}-0-request": self.req.pk,
                f"{prefix}-0-material": self.material.pk, f"{prefix}-0-quantity": "0.00",
                f"{prefix}-0-note": "Unrelated admin edit"}
        for quantity in ("0.00", "-1", "8"):
            data[f"{prefix}-0-quantity"] = quantity
            data[f"{prefix}-0-note"] = "Unrelated admin edit " + quantity
            formset = formset_class(data=data, instance=self.req)
            self.assertTrue(formset.is_valid(), formset.errors)
            formset.save()
            self.item.refresh_from_db()
            self.assertEqual(self.item.note, "Unrelated admin edit " + quantity)
            self.assertEqual(self.item.quantity, 0)

    def test_positive_item_cannot_be_changed_to_nonpositive_both_languages(self):
        for language, message in (("en", "Quantity must be greater than zero."),
                                  ("fr", "La quantité doit être supérieure à zéro.")):
            for quantity in (0, -1):
                with override(language), self.assertRaisesMessage(ValidationError, message):
                    self.item.quantity = quantity
                    self.item.save()
                self.item.refresh_from_db()
                self.assertEqual(self.item.quantity, 10)

    def test_legacy_zero_exception_does_not_allow_reference_or_negative_changes(self):
        self.legacy_zero()
        self.item.request_id = self.make_request()[0].pk
        with self.assertRaises(ValidationError):
            self.item.save()
        self.item.refresh_from_db()
        self.item.quantity = -1
        with self.assertRaises(ValidationError):
            self.item.save(update_fields=["note"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)

    def test_new_zero_entries_remain_invalid_in_model_and_form(self):
        for quantity in (0, -1):
            with self.assertRaises(ValidationError):
                RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=quantity)
        form = RequestMaterialItemForm(data={"material": self.material.pk, "quantity": "0", "note": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_request_admin_post_preserves_legacy_zero_while_editing_notes(self):
        self.legacy_zero()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse("admin:requests_app_request_change", args=[self.req.pk])
        response = self.client.get(url)
        form = response.context["adminform"].form
        data = {name: form[name].value() if form[name].value() is not None else ""
                for name in form.fields}
        data.update(description="Updated request description", _save="Save")
        for inline in response.context["inline_admin_formsets"]:
            formset = inline.formset
            for field in formset.management_form:
                data[field.html_name] = field.value()
            for inline_form in formset.forms:
                for field in inline_form:
                    data[field.html_name] = field.value() if field.value() is not None else ""
            if formset.model is RequestMaterialItem:
                data[formset.forms[0].add_prefix("note")] = "Updated historical note"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.req.refresh_from_db()
        self.assertEqual(self.req.description, "Updated request description")
        self.assertEqual(self.item.note, "Updated historical note")
        self.assertEqual(self.item.quantity, 0)

    def test_standalone_item_admin_legacy_notes_and_positive_validation(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse("admin:requests_app_requestmaterialitem_change", args=[self.item.pk])
        for language, message in (("en", "Quantity must be greater than zero."),
                                  ("fr", "La quantité doit être supérieure à zéro.")):
            response = self.client.post(url, {"request": self.req.pk, "material": self.material.pk,
                                              "quantity": "0", "note": "Invalid edit", "_save": "Save"},
                                        HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, message)
            self.item.refresh_from_db()
            self.assertEqual(self.item.quantity, 10)
        self.legacy_zero()
        for language in ("en", "fr"):
            response = self.client.post(url, {"request": self.req.pk, "material": self.material.pk,
                                              "quantity": "-1", "note": "Legacy note " + language, "_save": "Save"},
                                        HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 302)
            self.item.refresh_from_db()
            self.assertEqual(self.item.quantity, 0)
            self.assertEqual(self.item.note, "Legacy note " + language)

    def test_zero_history_presentation_and_excel_are_read_only_both_languages(self):
        self.issue()
        self.legacy_zero()
        StockMovement.objects.filter(request=self.req, movement_type="OUT").update(quantity=0)
        before = self.snapshot()
        self.client.force_login(self.user)
        for language in ("en", "fr"):
            for name, args in (("request_detail", [self.req.pk]),
                               ("approved_document", [self.req.pk]), ("material_reports", [])):
                response = self.client.get(reverse(name, args=args), HTTP_ACCEPT_LANGUAGE=language, follow=True)
                if name == "approved_document":
                    self.assertEqual(response.redirect_chain, [(reverse("material_document", args=[self.req.pk, "BS"]), 302)])
                self.assertEqual(response.status_code, 200, (name, language))
                self.assertContains(response, self.req.request_number)
            response = self.client.get(reverse("export_material_report_excel"),
                                       HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 200)
            workbook = load_workbook(BytesIO(response.content))
            rows = list(workbook.worksheets[0].values)
            matching = [row for row in rows if self.req.request_number in row]
            self.assertTrue(matching)
            self.assertTrue(all(row[9] == 0 for row in matching), matching)
        self.assertEqual(self.snapshot(), before)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)

    def test_zero_pair_does_not_block_other_material_return(self):
        self.issue()
        other = Material.objects.create(category=self.category, name="Legacy zero", code="ZERO", stock_quantity=50)
        zero = RequestMaterialItem.objects.create(request=self.req, material=other, quantity=1)
        RequestMaterialItem.objects.filter(pk=zero.pk).update(quantity=0)
        StockMovement.objects.create(request=self.req, material=other, movement_type="OUT", quantity=0)
        before = self.snapshot()
        with self.assertRaises(ValidationError):
            self.restore(1, item=zero)
        self.assertEqual(self.snapshot(), before)
        self.restore(2)
        self.assertEqual(self.balance(), 92)
        other.refresh_from_db()
        self.assertEqual(other.stock_quantity, 50)
        self.assertEqual(StockMovement.objects.filter(material=other).count(), 1)

    def test_partial_tokenless_history_with_false_flags_allows_remaining_returns(self):
        self.history([2, 3])
        self.assertEqual(material_return_totals(self.item)["remaining_quantity"], 5)
        self.restore(2)
        self.restore(3)
        self.assertEqual(self.balance(), 100)
        self.assertEqual(material_return_totals(self.item)["remaining_quantity"], 0)
        self.assertEqual(StockMovement.objects.filter(movement_type="RETURN", return_operation_token=None).count(), 2)
        self.req.refresh_from_db()
        self.assertFalse(self.req.stock_returned)
        self.assertIsNone(self.req.stock_returned_at)

    def test_full_tokenless_history_rejects_fresh_and_repeated_attempts_atomically(self):
        self.history([4, 6])
        self.assertEqual(material_return_totals(self.item)["remaining_quantity"], 0)
        before = self.snapshot()
        token = self.token()
        for retry in (token, token, self.token()):
            with self.assertRaises(ValidationError):
                self.restore(1, token=retry)
            self.assertEqual(self.snapshot(), before)
        self.req.refresh_from_db()
        self.assertFalse(self.req.stock_returned)
        self.assertIsNone(self.req.stock_returned_at)

    def test_duplicate_lines_issue_total_once_but_returns_require_review(self):
        RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=2)
        self.issue()
        self.assertEqual(self.balance(), 88)
        self.assertEqual(sorted(StockMovement.objects.values_list("quantity", flat=True)), [2, 10])
        before = self.snapshot()
        for item in self.req.material_items.all():
            with override("en"), self.assertRaisesMessage(ValidationError, "repeated material lines"):
                self.restore(1, item=item)
        self.assertEqual(self.snapshot(), before)

    def test_material_admin_direct_unvalidated_save_cannot_overwrite_balance(self):
        stale = Material.objects.get(pk=self.material.pk)
        self.issue()
        self.assertEqual(self.balance(), 90)
        stale.description = "Unrelated admin description"
        request = RequestFactory().post("/admin/inventory/material/")
        request.user = self.user
        with self.assertRaises(ValidationError):
            admin.site._registry[Material].save_model(request, stale, form=None, change=True)
        self.assertEqual(self.balance(), 90)
        self.assertEqual(StockMovement.objects.get(movement_type="OUT").quantity, 10)

    def admin_payload(self, language="en"):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse("admin:inventory_material_change", args=[self.material.pk])
        response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        data = {name: form[name].value() if form[name].value() is not None else ""
                for name in form.fields}
        data["_save"] = "Save"
        return url, data

    def test_stale_admin_post_after_issue_rejected_in_both_languages(self):
        payloads = [self.admin_payload(language) for language in ("en", "fr")]
        self.issue()
        before = self.snapshot()
        for language, (url, data), message in zip(("en", "fr"), payloads, (
                "Stock has changed since this form was opened.",
                "Le stock a changé depuis l’ouverture de ce formulaire.")):
            data["description"] = "Stale description"
            data["stock_quantity"] = "150"
            response = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, message)
            self.assertEqual(self.snapshot(), before)
            self.material.refresh_from_db()
            self.assertNotEqual(self.material.description, "Stale description")

    def test_fresh_admin_adjustment_then_stock_services_preserve_both_changes(self):
        url, data = self.admin_payload()
        data.update(stock_quantity="120.25", description="Authorized adjustment")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.balance(), Decimal("120.25"))
        self.issue()
        self.assertEqual(self.balance(), Decimal("110.25"))
        url, stale = self.admin_payload()
        self.restore(2)
        before = self.snapshot()
        stale["description"] = "Stale after return"
        response = self.client.post(url, stale)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.snapshot(), before)
        url, fresh = self.admin_payload()
        fresh["description"] = "Fresh note after return"
        self.assertEqual(self.client.post(url, fresh).status_code, 302)
        self.assertEqual(self.balance(), Decimal("112.25"))
        self.material.refresh_from_db()
        self.assertEqual(self.material.description, "Fresh note after return")

    def test_missing_or_tampered_balance_token_is_rejected(self):
        url, data = self.admin_payload()
        before = self.snapshot()
        for token in ("", data["original_stock"] + "tampered"):
            data["original_stock"] = token
            self.assertEqual(self.client.post(url, data).status_code, 200)
            self.assertEqual(self.snapshot(), before)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MaterialAdminLockTests(StockSafetyFixtures, TransactionTestCase):
    def test_form_validation_holds_material_lock_until_commit(self):
        from inventory.admin import MaterialAdminForm

        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        self.material.refresh_from_db()
        initial = MaterialAdminForm(instance=self.material)
        data = {name: initial[name].value() if initial[name].value() is not None else ""
                for name in initial.fields}

        def competing_lock():
            try:
                with transaction.atomic():
                    Material.objects.select_for_update(nowait=True).get(pk=self.material.pk)
                return True
            except DatabaseError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                form = MaterialAdminForm(data=data, instance=Material.objects.get(pk=self.material.pk))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertFalse(executor.submit(competing_lock).result(timeout=10))
                admin.site._registry[Material].save_model(RequestFactory().post("/admin/"), form.save(commit=False), form, True)
            self.assertTrue(executor.submit(competing_lock).result(timeout=10))
        self.issue()
        self.assertEqual(self.balance(), 90)


class LegacyStockMigrationTests(TransactionTestCase):
    """Run on Django's disposable test DB; restore the graph even on failure."""
    def test_0014_to_0016_preserves_zero_pairs_and_null_tokens(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        # Keep unrelated apps at their real schema state. A project_state with
        # only requests_app ancestors omits later independent accounts fields.
        other_leaves = [node for node in leaves if node[0] not in {"requests_app", "invoicing"}]
        old = other_leaves + [("requests_app", "0014_request_status_cancelled")]
        try:
            executor.migrate(old + [("invoicing", None)])
            apps = executor.loader.project_state(old).apps
            department = apps.get_model("accounts", "Department").objects.create(name="Synthetic", code="MIG")
            user = apps.get_model("accounts", "User").objects.create(username="migration-synthetic")
            kind = apps.get_model("requests_app", "RequestType").objects.create(name="Material", code="MIG", requires_materials=True)
            category = apps.get_model("inventory", "MaterialCategory").objects.create(name="Synthetic", code="MIG")
            ids = []
            for index in range(2):
                material = apps.get_model("inventory", "Material").objects.create(category=category, name="Synthetic", code=f"MIG{index}", stock_quantity=50)
                req = apps.get_model("requests_app", "Request").objects.create(
                    request_number=f"SYNTHETIC-MIG-{index}", request_type=kind, submitted_by=user,
                    department=department, request_for_department=department, description="Synthetic",
                    status="APPROVED", stock_deducted=True)
                item = apps.get_model("requests_app", "RequestMaterialItem").objects.create(request=req, material=material, quantity=0, note="Retain")
                movement = apps.get_model("requests_app", "StockMovement").objects.create(request=req, material=material, movement_type="OUT", quantity=0)
                ids.append((req.pk, material.pk, item.pk, movement.pk))
            for migration in ("0015_stock_return_retry_and_quantity_validation", "0016_protect_stock_movement_references"):
                executor = MigrationExecutor(connection)
                target = other_leaves + [("requests_app", migration)]
                executor.migrate(target)
                state = executor.loader.project_state(target).apps
                for request_id, material_id, item_id, movement_id in ids:
                    item = state.get_model("requests_app", "RequestMaterialItem").objects.get(pk=item_id)
                    movement = state.get_model("requests_app", "StockMovement").objects.get(pk=movement_id)
                    self.assertEqual((item.request_id, item.material_id, item.quantity, item.note), (request_id, material_id, Decimal("0.00"), "Retain"))
                    self.assertEqual((movement.request_id, movement.material_id, movement.quantity, movement.movement_type, movement.return_operation_token), (request_id, material_id, Decimal("0.00"), "OUT", None))
                    self.assertEqual(state.get_model("inventory", "Material").objects.get(pk=material_id).stock_quantity, 50)
                self.assertEqual(state.get_model("requests_app", "StockMovement").objects.count(), 2)
                self.assertEqual(state.get_model("requests_app", "RequestMaterialItem").objects.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(leaves)
