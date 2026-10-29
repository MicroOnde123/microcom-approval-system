from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from accounts.models import Department
from inventory.models import Material, MaterialCategory
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep
from .forms import RequestMaterialItemForm
from .models import Request, RequestApproval, RequestAuditLog, RequestMaterialItem, RequestType, StockMovement
from .services import approve_step, submit_request
from .stock_services import RETURN_TOKEN_SALT, deduct_material_stock, material_return_totals, return_material_stock


class StockSafetyFixtures:
    def setUp(self):
        super().setUp()
        self.department = Department.objects.create(name="Stock", code="SAFE")
        self.user = get_user_model().objects.create_user(
            username="stock", department=self.department, can_manage_stock=True)
        self.other = get_user_model().objects.create_user(username="other", department=self.department)
        self.request_type = RequestType.objects.create(name="Material", code="SAFE", requires_materials=True)
        self.workflow = ApprovalWorkflow.objects.create(name="Stock", request_type=self.request_type)
        ApprovalWorkflowStep.objects.create(workflow=self.workflow, step_order=1, approver_user=self.user)
        self.category = MaterialCategory.objects.create(name="Stock", code="SAFE")
        self.material = Material.objects.create(
            category=self.category, name="Router", code="SAFE", unit="pcs", stock_quantity=100)
        self.req, self.item = self.make_request()

    def make_request(self, quantity=10):
        req = Request.objects.create(
            request_number=str(uuid4()), submitted_by=self.other,
            department=self.department, request_type=self.request_type, description="Stock test")
        item = RequestMaterialItem.objects.create(request=req, material=self.material, quantity=quantity)
        submit_request(req)
        return req, item

    def issue(self, req=None):
        req = req or self.req
        approve_step(req.approvals.get(), self.user)
        req.refresh_from_db()

    def token(self, item=None, user=None):
        return signing.dumps({"item": (item or self.item).pk, "user": (user or self.user).pk,
                              "operation": str(uuid4())}, salt=RETURN_TOKEN_SALT)

    def restore(self, quantity, token=None, item=None):
        item = item or self.item
        return return_material_stock(item.pk, self.user, Decimal(str(quantity)), "Unused", token or self.token(item))

    def balance(self):
        self.material.refresh_from_db()
        return self.material.stock_quantity


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StockSafetyTests(StockSafetyFixtures, TestCase):
    def test_partial_return(self):
        self.issue()
        self.restore(3)
        self.assertEqual(self.balance(), 93)
        self.assertEqual(material_return_totals(self.item)["remaining_quantity"], 7)

    def test_full_return(self):
        self.issue()
        self.restore(10)
        self.assertEqual(self.balance(), 100)
        self.assertEqual(material_return_totals(self.item)["remaining_quantity"], 0)

    def test_multiple_returns_and_cumulative_limit(self):
        self.issue()
        self.restore(3)
        self.restore(4)
        with self.assertRaises(ValidationError):
            self.restore(4)
        self.restore(3)
        with self.assertRaises(ValidationError):
            self.restore(1)
        self.assertEqual(self.balance(), 100)
        self.assertEqual(StockMovement.objects.filter(movement_type="RETURN").count(), 3)

    def test_zero_negative_and_excess_precision_returns(self):
        self.issue()
        for quantity in (0, -1, Decimal("0.001")):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.restore(quantity)
        self.assertEqual(self.balance(), 90)

    def test_decimal_quantities(self):
        req, item = self.make_request(Decimal("0.25"))
        self.issue(req)
        self.restore("0.10", item=item)
        self.restore("0.15", item=item)
        self.assertEqual(self.balance(), 100)

    def test_unauthorized_service_and_url(self):
        self.issue()
        with self.assertRaises(PermissionDenied):
            return_material_stock(self.item.pk, self.other, 1, "Unused", self.token(user=self.other))
        self.client.force_login(self.other)
        url = reverse("return_material_to_stock", args=[self.item.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(self.balance(), 90)

    def test_unapproved_request(self):
        with self.assertRaises(ValidationError):
            self.restore(1)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("return_material_to_stock", args=[self.item.pk])).status_code, 404)

    def test_stock_not_issued_or_missing_movement(self):
        self.req.status = "APPROVED"
        self.req.save()
        with self.assertRaises(ValidationError):
            self.restore(1)
        self.req.stock_deducted = True
        self.req.save()
        with self.assertRaises(ValidationError):
            self.restore(1)
        self.assertEqual(self.balance(), 100)

    def test_legacy_returns_count_without_tokens(self):
        self.issue()
        StockMovement.objects.create(request=self.req, material=self.material, movement_type="RETURN", quantity=8)
        with self.assertRaises(ValidationError):
            self.restore(3)
        self.restore(2)
        self.assertEqual(material_return_totals(self.item)["remaining_quantity"], 0)

    def test_inconsistent_history_is_blocked(self):
        self.issue()
        for quantity in (-1, 11):
            movement = StockMovement.objects.create(
                request=self.req, material=self.material, movement_type="RETURN", quantity=quantity)
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.restore(1)
            movement.delete()
        StockMovement.objects.filter(movement_type="OUT").update(quantity=9)
        with self.assertRaises(ValidationError):
            self.restore(1)

    def test_repeated_material_lines_block_returns_without_guessing(self):
        RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=2)
        self.issue()
        self.assertEqual(self.balance(), 88)
        with self.assertRaisesMessage(ValidationError, "repeated material lines"):
            self.restore(1)
        self.assertFalse(StockMovement.objects.filter(movement_type="RETURN").exists())

    def test_return_audit_failure_rolls_back_and_retry_succeeds(self):
        self.issue()
        token = self.token()
        with patch("requests_app.stock_services.RequestAuditLog.objects.create", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.restore(3, token)
        self.assertEqual(self.balance(), 90)
        self.assertFalse(StockMovement.objects.filter(movement_type="RETURN").exists())
        self.assertTrue(self.restore(3, token)[1])

    def test_return_movement_failure_rolls_back(self):
        self.issue()
        with patch("requests_app.stock_services.StockMovement.objects.create", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.restore(3)
        self.assertEqual(self.balance(), 90)
        self.assertFalse(RequestAuditLog.objects.filter(action="STOCK_RETURNED").exists())

    def test_retry_token_and_distinct_equal_returns(self):
        self.issue()
        token = self.token()
        movement, created = self.restore(3, token)
        repeated, created_again = self.restore(3, token)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(movement.pk, repeated.pk)
        self.restore(3)
        self.assertEqual(self.balance(), 96)
        self.assertEqual(RequestAuditLog.objects.filter(action="STOCK_RETURNED").count(), 2)

    def test_full_return_retry_and_blank_reason(self):
        self.issue()
        with self.assertRaises(ValidationError):
            return_material_stock(self.item.pk, self.user, 1, " ", self.token())
        token = self.token()
        self.restore(10, token)
        self.assertFalse(self.restore(10, token)[1])
        self.assertEqual(self.balance(), 100)

    def test_superuser_return_permission(self):
        self.issue()
        self.other.is_superuser = True
        self.other.save()
        _, created = return_material_stock(self.item.pk, self.other, 1, "Unused", self.token(user=self.other))
        self.assertTrue(created)
        self.assertEqual(self.balance(), 91)

    def test_invalid_return_posts_do_not_change_stock(self):
        self.issue()
        self.client.force_login(self.user)
        url = reverse("return_material_to_stock", args=[self.item.pk])
        for quantity, token in (("0", self.token()), ("-1", self.token()), ("1", "invalid"), ("1", "")):
            with self.subTest(quantity=quantity, token=token):
                response = self.client.post(url, {"quantity": quantity, "reason": "Unused", "operation_token": token})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(self.balance(), 90)

    def test_positive_quantity_messages_are_bilingual(self):
        for language, message in (("en", "Quantity must be greater than zero."),
                                  ("fr", "La quantité doit être supérieure à zéro.")):
            with self.subTest(language=language), override(language):
                form = RequestMaterialItemForm(data={"material": self.material.pk, "quantity": "-1"})
                self.assertFalse(form.is_valid())
                self.assertIn(message, form.errors["quantity"])

    def test_invalid_wrong_item_wrong_user_and_expired_tokens(self):
        self.issue()
        _, other_item = self.make_request()
        tokens = ["invalid", self.token(other_item), self.token(user=self.other)]
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(ValidationError):
                self.restore(1, token)
        with patch("django.core.signing.time.time", return_value=1):
            expired = self.token()
        with self.assertRaises(ValidationError):
            self.restore(1, expired)

    def test_duplicate_post_and_new_form_same_quantity(self):
        self.issue()
        self.client.force_login(self.user)
        url = reverse("return_material_to_stock", args=[self.item.pk])
        response = self.client.get(url)
        token = response.context["form"].initial["operation_token"]
        data = {"quantity": "3", "reason": "Unused", "operation_token": token}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.balance(), 93)
        data["operation_token"] = self.client.get(url).context["form"].initial["operation_token"]
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.balance(), 96)

    def test_return_screen_totals_and_translations(self):
        self.issue()
        self.restore(3)
        self.client.force_login(self.user)
        url = reverse("return_material_to_stock", args=[self.item.pk])
        for language, label in (("en", "Remaining Returnable Quantity"), ("fr", "Quantité restante pouvant être retournée")):
            with self.subTest(language=language), override(language):
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, label)
                self.assertEqual(response.context["issued_quantity"], 10)
                self.assertEqual(response.context["returned_quantity"], 3)
                self.assertEqual(response.context["remaining_quantity"], 7)
        with override("fr"), self.assertRaisesMessage(ValidationError, "restent disponibles"):
            self.restore(8)

    def test_positive_form_model_and_service_validation(self):
        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                form = RequestMaterialItemForm(data={"material": self.material.pk, "quantity": quantity})
                self.assertFalse(form.is_valid())
                item = RequestMaterialItem(request=self.req, material=self.material, quantity=quantity)
                with self.assertRaises(ValidationError):
                    item.full_clean()
                with self.assertRaises(ValidationError):
                    item.save()
                # Simulate pre-existing bad data or a direct SQL/import bypass.
                RequestMaterialItem.objects.filter(pk=self.item.pk).update(quantity=quantity)
                with self.assertRaises(ValidationError):
                    deduct_material_stock(self.req)
                self.assertEqual(self.balance(), 100)

    def test_submission_revalidates_historical_quantities(self):
        self.req.approvals.all().delete()
        RequestMaterialItem.objects.filter(pk=self.item.pk).update(quantity=-2)
        with self.assertRaises(ValidationError):
            submit_request(self.req)
        self.assertFalse(self.req.approvals.exists())

    def test_normal_final_approval_and_duplicate_deduction(self):
        approval = self.req.approvals.get()
        stale = Request.objects.get(pk=self.req.pk)
        self.issue()
        deduct_material_stock(stale)
        with self.assertRaises(ValidationError):
            approve_step(approval, self.user)
        self.assertEqual(self.balance(), 90)
        self.assertEqual(StockMovement.objects.filter(movement_type="OUT").count(), 1)
        self.assertEqual(StockMovement.objects.get().performed_by, self.user)
        self.assertEqual(self.req.status, "APPROVED")

    def test_insufficient_stock_rolls_back_approval(self):
        self.material.stock_quantity = 9
        self.material.save()
        with self.assertRaises(ValidationError):
            self.issue()
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "IN_REVIEW")
        self.assertEqual(self.req.approvals.get().status, "PENDING")
        self.assertFalse(self.req.stock_deducted)
        self.assertFalse(StockMovement.objects.exists())

    def test_multiple_materials_and_failure_rollback(self):
        other = Material.objects.create(category=self.category, name="Cable", code="CABLE", stock_quantity=20)
        RequestMaterialItem.objects.create(request=self.req, material=other, quantity=Decimal("1.25"))
        create = StockMovement.objects.create
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError("failure")
            return create(**kwargs)

        with patch("requests_app.stock_services.StockMovement.objects.create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.issue()
        other.refresh_from_db()
        self.assertEqual(other.stock_quantity, 20)
        self.assertEqual(self.balance(), 100)
        self.assertFalse(StockMovement.objects.exists())
        self.assertEqual(self.req.approvals.get().status, "PENDING")
        self.issue()
        other.refresh_from_db()
        self.assertEqual(other.stock_quantity, Decimal("18.75"))
        self.assertEqual(self.balance(), 90)

    def test_duplicate_material_rows_revalidate_combined_quantity(self):
        RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=95)
        with self.assertRaises(ValidationError):
            self.issue()
        self.assertEqual(self.balance(), 100)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locking is required")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StockConcurrencyTests(StockSafetyFixtures, TransactionTestCase):
    def race(self, operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=10)
                try:
                    operation()
                    return "accepted"
                except ValidationError:
                    return "rejected"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            futures = [executor.submit(run, operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]

    def test_competing_final_approvals_cannot_overspend(self):
        self.material.stock_quantity = 15
        self.material.save()
        second, _ = self.make_request(10)
        approvals = [self.req.approvals.get(), second.approvals.get()]
        results = self.race([lambda a=a: approve_step(a, self.user) for a in approvals])
        self.assertCountEqual(results, ["accepted", "rejected"])
        self.assertEqual(self.balance(), 5)
        self.assertEqual(StockMovement.objects.filter(movement_type="OUT").count(), 1)

    def test_same_approval_is_processed_once(self):
        approval = self.req.approvals.get()
        results = self.race([lambda: approve_step(approval, self.user)] * 2)
        self.assertCountEqual(results, ["accepted", "rejected"])
        self.assertEqual(self.balance(), 90)

    def test_competing_returns_cannot_exceed_issue(self):
        self.issue()
        tokens = [self.token(), self.token()]
        results = self.race([lambda t=t: self.restore(7, t) for t in tokens])
        self.assertCountEqual(results, ["accepted", "rejected"])
        self.assertEqual(self.balance(), 97)
        self.assertEqual(StockMovement.objects.filter(movement_type="RETURN").count(), 1)

    def test_same_return_token_is_processed_once(self):
        self.issue()
        token = self.token()
        self.assertEqual(self.race([lambda: self.restore(3, token)] * 2), ["accepted", "accepted"])
        self.assertEqual(self.balance(), 93)
        self.assertEqual(StockMovement.objects.filter(movement_type="RETURN").count(), 1)

    def test_distinct_equal_returns_both_succeed(self):
        self.issue()
        tokens = [self.token(), self.token()]
        self.assertEqual(self.race([lambda t=t: self.restore(3, t) for t in tokens]), ["accepted", "accepted"])
        self.assertEqual(self.balance(), 96)

    def test_opposite_material_line_order_does_not_deadlock(self):
        other = Material.objects.create(category=self.category, name="Cable", code="OTHER", stock_quantity=100)
        second, _ = self.make_request()
        RequestMaterialItem.objects.create(request=self.req, material=other, quantity=1)
        second.material_items.all().delete()
        RequestMaterialItem.objects.create(request=second, material=other, quantity=1)
        RequestMaterialItem.objects.create(request=second, material=self.material, quantity=10)
        approvals = [self.req.approvals.get(), second.approvals.get()]
        self.assertEqual(self.race([lambda a=a: approve_step(a, self.user) for a in approvals]), ["accepted", "accepted"])
        self.assertEqual(self.balance(), 80)
        other.refresh_from_db()
        self.assertEqual(other.stock_quantity, 98)

    def test_return_and_issue_share_material_lock(self):
        self.issue()
        second, _ = self.make_request()
        approval = second.approvals.get()
        token = self.token()
        self.assertEqual(self.race([lambda: self.restore(3, token),
                                    lambda: approve_step(approval, self.user)]), ["accepted", "accepted"])
        self.assertEqual(self.balance(), 83)
