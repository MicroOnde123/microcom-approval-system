from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from .entry_services import create_category
from .entry_views import create_material_category
from .models import Material, MaterialCategory, MaterialReceipt, MaterialReceiptLine
from .test_material_entries import Fixtures
from requests_app.models import StockMovement


class CategoryCreationTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("create_material_category")
        self.payload = {"category-name": "Cables", "category-code": "CABLES", "category-description": "Network supplies"}

    def test_create_and_retry_never_touch_stock(self):
        before = list(Material.objects.values())
        response = self.client.post(self.url, {**self.payload, "material": self.material.pk,
                                               "quantity": "999", "mode": "existing"})
        self.assertEqual(response.status_code, 201)
        category = MaterialCategory.objects.get(code="CABLES")
        self.assertEqual(category.name, "Cables")
        self.assertEqual(category.description, "Network supplies")
        for _ in range(2):
            retry = self.client.post(self.url, self.payload)
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(retry.json()["category"]["id"], category.pk)
        self.assertEqual(MaterialCategory.objects.filter(code="CABLES").count(), 1)
        self.assertEqual(list(Material.objects.values()), before)
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(MaterialReceipt.objects.exists())
        self.assertFalse(MaterialReceiptLine.objects.exists())

    def test_duplicate_code_does_not_overwrite(self):
        response = self.client.post(self.url, {**self.payload, "category-code": self.category.code})
        self.assertEqual(response.status_code, 409)
        self.assertIn("code", response.json()["errors"])
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Tools")

    def test_invalid_fields_and_optional_description(self):
        for changes, field in [({"category-name": "   "}, "name"), ({"category-code": ""}, "code"), ({"category-name": "a" * 101}, "name"), ({"category-code": "a" * 31}, "code"), ({"category-code": "bad\x00code"}, "code")]:
            with self.subTest(changes=changes):
                response = self.client.post(self.url, {**self.payload, **changes})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["errors"])
        response = self.client.post(self.url, {"category-name": " Other ", "category-code": " OTHER "})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(MaterialCategory.objects.get(code="OTHER").description, "")

    def test_authentication_permissions_and_post_only(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 302)
        for active, manager, superuser, allowed in [(True, False, False, False), (False, True, True, False), (True, True, False, True), (True, False, True, True)]:
            actor = get_user_model().objects.create_user(username=f"actor-{active}-{manager}-{superuser}", is_active=active, can_manage_stock=manager, is_superuser=superuser)
            request = RequestFactory().post(self.url, self.payload)
            request.user = actor
            request._dont_enforce_csrf_checks = True
            data = {"name": "Allowed", "code": "ALLOWED"}
            if allowed:
                self.assertIn(create_material_category(request).status_code, (200, 201))
                create_category(user=actor, data=data)
            else:
                with self.assertRaises(PermissionDenied): create_material_category(request)
                with self.assertRaises(PermissionDenied): create_category(user=actor, data=data)
        self.client.force_login(self.user)
        for method in ("get", "put", "delete"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)

    def test_csrf_required_and_valid_token_works(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload).status_code, 403)
        client.get(reverse("material_entries"))
        response = client.post(self.url, self.payload, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 201)

    def test_language_modal_and_duplicate_errors(self):
        for language, label in [("en", "+ New Category"), ("fr", "+ Nouvelle cat\u00e9gorie")]:
            self.client.cookies["django_language"] = language
            response = self.client.get(reverse("material_entries"))
            self.assertContains(response, label)
            self.assertContains(response, 'aria-labelledby="category-title"')
            self.assertContains(response, 'id="category-form"')
            self.assertContains(response, self.url)
            response = self.client.post(self.url, {**self.payload, "category-code": self.category.code})
            error = response.json()["errors"]["code"][0]
            self.assertIn("code" if language == "en" else "cat\u00e9gorie", error)
        self.assertNotContains(self.client.get(reverse("material_entries") + "?mode=existing"), 'id="category-dialog"')

    def test_posted_material_and_stock_values_remain_on_validation_error(self):
        from .entry_services import new_token
        payload = {**self.new, **self.data, "mode": "new", "code": "", "token": new_token(self.user, "new")}
        response = self.client.post(reverse("material_entries"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["material_form"]["name"].value(), "Bolt")
        for field, value in self.data.items():
            self.assertEqual(response.context["receipt_form"][field].value(), value)
        self.assertContains(response, 'id="category-dialog"')
        self.assertFalse(MaterialReceipt.objects.exists())


@skipUnless(connection.vendor == "postgresql", "PostgreSQL concurrent unique inserts required")
class ConcurrentCategoryTests(Fixtures, TransactionTestCase):
    def test_simultaneous_identical_requests(self):
        barrier = Barrier(2)
        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                category, created = create_category(user=self.user, data={"name": "Concurrent", "code": "CONCURRENT"})
                return category.pk, created
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(MaterialCategory.objects.filter(code="CONCURRENT").count(), 1)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 10)
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(MaterialReceipt.objects.exists())
