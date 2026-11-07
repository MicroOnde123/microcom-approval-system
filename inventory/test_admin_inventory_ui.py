"""Existing Material Admin presentation; PostgreSQL safeguards tested separately."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from inventory.models import Material
from inventory.test_pricing import PricingFixtures


class MaterialAdminUITests(PricingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("admin:inventory_material_changelist")
        self.material.minimum_stock_level = 10
        self.material.save()
        for code, quantity, minimum, active in [("ZERO", "0", "0", True), ("NEG", "-1", "0", False),
                ("LOW", "0.01", "1", True), ("HIGH", "10.01", "10", False), ("NO-MIN", "1", "0", True)]:
            Material.objects.create(name=code, code=code, category=self.category, stock_quantity=Decimal(quantity),
                minimum_stock_level=Decimal(minimum), unit="m", is_active=active)

    def ids(self, **query):
        return {m.code for m in self.client.get(self.url, query).context["cl"].result_list}

    def test_stock_status_boundaries_and_existing_filters(self):
        self.assertEqual(self.ids(stock_status="out"), {"ZERO", "NEG"})
        self.assertEqual(self.ids(stock_status="low"), {"PRICE-1", "LOW"})
        self.assertEqual(self.ids(stock_status="available"), {"HIGH", "NO-MIN"})
        self.assertEqual(len(self.ids(stock_status="invalid")), 6)
        self.assertEqual(self.ids(is_active__exact="0"), {"NEG", "HIGH"})
        self.assertEqual(self.ids(q="PRICE-1"), {"PRICE-1"})
        self.assertEqual(self.ids(q="Cable"), {"PRICE-1"})
        self.assertEqual(self.ids(category__id__exact=self.category.pk, stock_status="out"), {"ZERO", "NEG"})

    def test_list_and_edit_render_with_localized_sections_and_hidden_revision_tokens(self):
        for lang in ("en", "fr"):
            self.client.cookies["django_language"] = lang
            response = self.client.get(self.url)
            self.assertContains(response, "css/admin_material.css")
            self.assertContains(response, "material-stock-status--out")
            self.assertContains(response, "material-stock-status--low")
            self.assertContains(response, "material-stock-status--available")
            self.assertContains(response, 'class="sortable column-active_status"', count=1)
            self.assertContains(response, "Au-dessus du seuil minimum" if lang == "fr" else "Above minimum")
            self.assertContains(response, "Quantit\u00e9 en stock" if lang == "fr" else "Stock quantity")
            self.assertContains(response, reverse("admin:inventory_material_change", args=[self.material.pk]))
            edit = self.client.get(reverse("admin:inventory_material_change", args=[self.material.pk]))
            self.assertContains(edit, "Prix catalogue" if lang == "fr" else "Catalogue price")
            for name in ("original_stock", "original_price", "original_catalogue"):
                self.assertContains(edit, 'type="hidden" name="' + name + '"')
            self.assertContains(edit, 'name="stock_quantity"')
            self.assertContains(edit, 'name="price_change_reason"')
            self.assertContains(edit, 'material-revisions')

    def test_permissions_are_unchanged_and_view_only_users_cannot_edit(self):
        viewer = get_user_model().objects.create_user(username="inventory-viewer", is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(codename="view_material"))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        edit = reverse("admin:inventory_material_change", args=[self.material.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        self.assertEqual(self.client.post(edit, {"stock_quantity": "999"}).status_code, 403)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 10)

    def test_category_rendering_does_not_query_per_row(self):
        from django.contrib import admin
        from inventory.admin import MaterialAdmin
        from django.test import RequestFactory
        config = MaterialAdmin(Material, admin.site)
        request = RequestFactory().get(self.url); request.user = self.user
        with self.assertNumQueries(1):
            rows = list(config.get_queryset(request).select_related(*config.list_select_related))
            for obj in rows:
                config.material_category(obj)
                config.stock_balance(obj)
                config.stock_status(obj)
