from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Request, RequestMaterialItem, StockMovement
from .test_stock_safety import StockSafetyFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DraftHardeningTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.other)

    def payload(self, url, quantity, existing=False, language="en"):
        response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
        data = {
            "action": "save_draft", "submission_token": response.context["submission_token"],
            "request_type": self.request_type.pk, "request_for_department": self.department.pk,
            "description": "Changed draft header", "material_items-TOTAL_FORMS": "1",
            "material_items-INITIAL_FORMS": "1" if existing else "0",
            "material_items-0-material": self.material.pk,
            "material_items-0-quantity": quantity, "material_items-0-note": "New note",
        }
        if existing:
            data["material_items-0-id"] = self.item.pk
        return data

    def draft(self):
        self.req.status = "DRAFT"
        self.req.save()
        self.req.approvals.all().delete()
        return reverse("edit_request", args=[self.req.pk])

    def assert_unchanged(self, request_count, item_count):
        self.assertEqual(Request.objects.count(), request_count)
        self.assertEqual(RequestMaterialItem.objects.count(), item_count)
        self.assertFalse(StockMovement.objects.exists())

    def test_invalid_draft_creation_is_localized_and_writes_nothing(self):
        url = reverse("create_request")
        for language in ("en", "fr"):
            for quantity in ("0.001", "0", "-1", "not-a-number", "100000000"):
                with self.subTest(language=language, quantity=quantity):
                    data = self.payload(url, quantity, language=language)
                    response = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.status_code, 200)
                    errors = response.context["formset"].forms[0].errors
                    self.assertIn("quantity", errors)
                    if quantity in ("0", "-1"):
                        self.assertContains(response, "La quantité doit être supérieure à zéro."
                                            if language == "fr" else "Quantity must be greater than zero.")
                    if quantity == "0.001":
                        self.assertContains(response, "Utilisez au maximum deux décimales pour la quantité."
                                            if language == "fr" else "Use at most two decimal places for the quantity.")
                    if quantity == "not-a-number":
                        self.assertContains(response, "Saisissez une quantité valide."
                                            if language == "fr" else "Enter a valid quantity.")
                    if quantity == "100000000":
                        self.assertContains(response, "La quantité est trop élevée."
                                            if language == "fr" else "The quantity is too large.")
                    self.assert_unchanged(1, 1)

    def test_invalid_draft_edit_preserves_header_and_lines(self):
        url = self.draft()
        original_description = self.req.description
        for language in ("en", "fr"):
            for quantity in ("0.001", "0", "-1", "not-a-number"):
                with self.subTest(language=language, quantity=quantity):
                    data = self.payload(url, quantity, existing=True, language=language)
                    # A deletion preceding an invalid new line must not persist either.
                    data.update({"material_items-TOTAL_FORMS": "2",
                                 "material_items-0-DELETE": "on",
                                 "material_items-1-material": self.material.pk,
                                 "material_items-1-quantity": quantity})
                    response = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.status_code, 200)
                    self.req.refresh_from_db()
                    self.item.refresh_from_db()
                    self.assertEqual(self.req.description, original_description)
                    self.assertEqual(self.req.status, "DRAFT")
                    self.assertEqual(self.item.quantity, 10)
                    self.assert_unchanged(1, 1)

    def test_invalid_second_line_does_not_save_valid_first_line(self):
        url = reverse("create_request")
        data = self.payload(url, "1.25")
        data.update({"material_items-TOTAL_FORMS": "2",
                     "material_items-1-material": self.material.pk,
                     "material_items-1-quantity": "0.001"})
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assert_unchanged(1, 1)

    def test_valid_decimal_draft_creation_and_retry(self):
        url = reverse("create_request")
        data = self.payload(url, "1.25")
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        created = Request.objects.exclude(pk=self.req.pk).get()
        self.assertEqual(created.status, "DRAFT")
        self.assertFalse(created.approvals.exists())
        self.assertEqual(created.material_items.get().quantity, Decimal("1.25"))
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assert_unchanged(2, 2)

    def test_valid_decimal_draft_edit(self):
        url = self.draft()
        data = self.payload(url, "2.75", existing=True)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.req.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.req.description, "Changed draft header")
        self.assertEqual(self.item.quantity, Decimal("2.75"))
        self.assertEqual(self.req.status, "DRAFT")
        self.assertFalse(self.req.approvals.exists())

    def test_draft_success_messages_are_bilingual(self):
        url = reverse("create_request")
        for language, message in (("en", "Draft saved successfully."),
                                  ("fr", "Brouillon enregistré avec succès.")):
            with self.subTest(language=language):
                data = self.payload(url, "1.25", language=language)
                response = self.client.post(url, data, follow=True, HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, message)

    def test_draft_can_exceed_stock_and_keep_incomplete_rows(self):
        url = reverse("create_request")
        data = self.payload(url, "101.25")
        data.update({"material_items-TOTAL_FORMS": "3",
                     "material_items-1-material": self.material.pk,
                     "material_items-1-quantity": "",
                     "material_items-2-material": "", "material_items-2-quantity": "2"})
        self.assertEqual(self.client.post(url, data).status_code, 302)
        draft = Request.objects.exclude(pk=self.req.pk).get()
        self.assertEqual(draft.material_items.get().quantity, Decimal("101.25"))
        self.assertEqual(draft.status, "DRAFT")
        data = self.payload(reverse("edit_request", args=[draft.pk]), "101.25")
        data["action"] = "submit"
        self.assertEqual(self.client.post(reverse("edit_request", args=[draft.pk]), data).status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "DRAFT")

    def test_model_validation_failure_rolls_back_creation(self):
        url = reverse("create_request")
        data = self.payload(url, "1.25")
        with patch("requests_app.views.save_complete_draft_material_rows",
                   side_effect=ValidationError("Quantity must be greater than zero.")):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assert_unchanged(1, 1)

    def test_late_validation_failure_rolls_back_edit(self):
        url = self.draft()
        data = self.payload(url, "1.25", existing=True)
        original_save = RequestMaterialItem.save

        def save_then_fail(item, *args, **kwargs):
            original_save(item, *args, **kwargs)
            raise ValidationError("Quantity must be greater than zero.")

        with patch.object(RequestMaterialItem, "save", save_then_fail):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.req.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.req.description, "Stock test")
        self.assertEqual(self.item.quantity, 10)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MovementAdminHardeningTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.issue()
        self.restore(3)
        self.movement = StockMovement.objects.get(movement_type="RETURN")
        self.user.is_staff = True
        self.user.save()
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="requests_app", content_type__model="stockmovement"))
        self.client.force_login(self.user)

    def assert_intact(self):
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.quantity, 3)
        self.assertEqual(self.movement.movement_type, "RETURN")
        self.assertEqual(self.movement.material_id, self.material.pk)
        self.assertEqual(self.movement.request_id, self.req.pk)
        self.assertIsNotNone(self.movement.return_operation_token)
        self.assertEqual(self.balance(), 93)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_authorized_staff_can_view_read_only(self):
        response = self.client.get(reverse("admin:requests_app_stockmovement_change", args=[self.movement.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_change_permission"])
        self.assertFalse(response.context["has_delete_permission"])
        self.assertNotContains(response, 'name="quantity"')
        self.assertContains(response, str(self.movement.return_operation_token))
        self.assertEqual(self.client.get(reverse("admin:requests_app_stockmovement_changelist")).status_code, 200)

    def test_direct_edit_post_is_denied_even_with_model_permissions(self):
        url = reverse("admin:requests_app_stockmovement_change", args=[self.movement.pk])
        response = self.client.post(url, {"quantity": "99", "movement_type": "OUT", "material": "",
                                          "request": "", "return_operation_token": str(uuid4()),
                                          "return_reason": "Altered", "_save": "Save"})
        self.assertEqual(response.status_code, 403)
        self.assert_intact()

    def test_single_delete_get_and_post_are_denied(self):
        url = reverse("admin:requests_app_stockmovement_delete", args=[self.movement.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assert_intact()

    def test_bulk_delete_is_not_available_or_executable(self):
        url = reverse("admin:requests_app_stockmovement_changelist")
        response = self.client.post(url, {"action": "delete_selected", "_selected_action": [self.movement.pk], "post": "yes"})
        self.assertIn(response.status_code, (200, 302))
        self.assert_intact()

    def test_superuser_cannot_edit_delete_or_add_movements(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        for action, data in (("change", {"quantity": 99, "_save": "Save"}), ("delete", {"post": "yes"})):
            with self.subTest(action=action):
                url = reverse("admin:requests_app_stockmovement_" + action, args=[self.movement.pk])
                self.assertEqual(self.client.post(url, data).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:requests_app_stockmovement_add"), {}).status_code, 403)
        self.assert_intact()

    def test_services_still_create_movements_and_retries_are_preserved(self):
        token = self.token()
        movement, created = self.restore(2, token)
        self.assertTrue(created)
        self.assertFalse(self.restore(2, token)[1])
        self.assertEqual(self.balance(), 95)
        self.assertEqual(StockMovement.objects.filter(pk=movement.pk).count(), 1)

    def test_request_admin_delete_cannot_clear_movement_references(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse("admin:requests_app_request_delete", args=[self.req.pk])
        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["protected"])
        self.assertTrue(Request.objects.filter(pk=self.req.pk).exists())
        self.assert_intact()

    def test_material_admin_delete_cannot_cascade_delete_movements(self):
        from inventory.models import Material
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        # An IN movement without request lines previously allowed cascade deletion.
        material = Material.objects.create(category=self.category, name="Spare", code="SPARE")
        movement = StockMovement.objects.create(material=material, movement_type="IN", quantity=1)
        url = reverse("admin:inventory_material_delete", args=[material.pk])
        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["protected"])
        self.assertTrue(Material.objects.filter(pk=material.pk).exists())
        self.assertTrue(StockMovement.objects.filter(pk=movement.pk).exists())
