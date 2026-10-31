"""Presentation and POST regression coverage, using synthetic isolated fixtures."""
from uuid import uuid4
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.messages import get_messages
from inventory.models import Material
from .models import RequestMaterialItem, StockMovement, ReturnReceipt, MaterialReconciliation
from .test_material_outcomes import OutcomeFixtures


class MaterialOperationsUiTests(OutcomeFixtures, TestCase):
    def test_fully_returned_material_has_zero_usage_without_destination(self):
        self.restore(10)
        response = self.client.get(reverse("material_outcomes", args=[self.req.pk]))
        self.assertContains(response, "No usage destination is required")
        form = response.context["form"]
        for outcome in ("CLIENT", "MICROCOM", "RETAINED"):
            self.assertEqual(form[f"item_{self.item.pk}_{outcome}"].value(), 0)
        self.assertEqual(form[f"item_{self.item.pk}_RETURNED"].value(), 10)
        self.assertEqual(self.balance(), 100)

    def test_overview_separates_destinations_and_keeps_revision_after_full_return(self):
        revision = self.reconcile(self.allocations(client=3, microcom=2))
        response = self.client.get(reverse("material_outcomes", args=[self.req.pk]))
        row = response.context["material_rows"][0]
        self.assertEqual((row["client"], row["microcom"], row["outstanding"]), (3, 2, 5))
        self.restore(10)
        response = self.client.get(reverse("material_outcomes", args=[self.req.pk]))
        form = response.context["form"]
        self.assertEqual(form[f"item_{self.item.pk}_CLIENT"].value(), 0)
        self.assertEqual(form[f"item_{self.item.pk}_MICROCOM"].value(), 0)
        self.assertEqual(revision.lines.get(outcome="CLIENT").quantity, 3)
        self.assertEqual(revision.lines.get(outcome="MICROCOM").quantity, 2)
        self.assertEqual(MaterialReconciliation.objects.count(), 1)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("material_outcomes", args=[self.req.pk])

    def test_compact_status_and_collapsed_sections_without_return(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="material-status"')
        self.assertContains(response, 'role="tab"', count=3)
        self.assertContains(response, 'role="tabpanel"', count=3)
        self.assertEqual(response.context["active_tab"], "overview")
        self.assertContains(response, 'data-quick-outcome')
        self.assertContains(response, 'data-review-dialog')
        self.assertContains(response, "Not yet reconciled")
        self.assertContains(response, "No undocumented physical returns are available.")
        self.assertFalse(ReturnReceipt.objects.exists())
        self.assertFalse(MaterialReconciliation.objects.exists())

    def test_partial_return_maximum_and_visible_form(self):
        self.restore(3)
        response = self.client.get(reverse("return_material_to_stock", args=[self.item.pk]))
        self.assertContains(response, 'max="7.00"')
        self.assertContains(response, 'name="quantity"')
        self.assertContains(response, "Confirm return to stock")
        self.assertContains(response, reverse("request_detail", args=[self.req.pk]))

    def test_fully_returned_hides_form_and_rejects_extra_post(self):
        original_token = self.token()
        self.restore(10, token=original_token)
        url = reverse("return_material_to_stock", args=[self.item.pk])
        response = self.client.get(url)
        self.assertContains(response, "All issued quantities have already been returned.")
        self.assertNotContains(response, 'name="quantity"')
        before = self.balance()
        response = self.client.post(url, {"quantity": "1", "reason": "Extra", "operation_token": self.token()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertNotContains(response, 'name="quantity"')
        self.assertEqual(self.balance(), before)
        replay = self.client.post(url, {"quantity": "10", "reason": "Unused", "operation_token": original_token})
        self.assertEqual(replay.status_code, 302)
        self.assertEqual(StockMovement.objects.filter(movement_type="RETURN").count(), 1)
        self.assertEqual(self.balance(), before)

    def test_return_post_success_and_excess_quantity_feedback(self):
        url = reverse("return_material_to_stock", args=[self.item.pk])
        response = self.client.post(url, {"quantity": "11", "reason": "Unused", "operation_token": self.token()})
        self.assertContains(response, "remain available to return")
        self.assertEqual(self.balance(), 90)
        response = self.client.post(url, {"quantity": "2", "reason": "Unused", "operation_token": self.token(), "next": self.url})
        self.assertRedirects(response, self.url)
        self.assertTrue(any("successfully" in str(message) for message in get_messages(response.wsgi_request)))
        self.assertEqual(self.balance(), 92)

    def test_mixed_revision_and_new_returns_show_review_required(self):
        self.restore(2)
        self.reconcile(self.allocations(returned=2, client=3, microcom=2))
        self.restore(1)
        response = self.client.get(self.url)
        self.assertContains(response, "Review required")
        self.assertEqual(response.context["form"][f"item_{self.item.pk}_RETURNED"].value(), 3)
        self.assertContains(response, 'readonly')
        self.assertContains(response, 'id="reconciliation-history"')

    def test_reconciliation_post_retains_errors_then_saves_once(self):
        data = {"action": "reconcile", "token": str(uuid4()), "revision": "0", "reason": "Mixed use"}
        data.update({f"item_{self.item.pk}_{key}": str(value) for key,value in self.allocations(client=3, microcom=2)[self.item.pk].items()})
        invalid = dict(data, reason="")
        response = self.client.post(self.url, invalid)
        self.assertEqual(response.context["active_tab"], "reconcile")
        self.assertContains(response, "This field is required.")
        self.assertEqual(str(response.context["form"]["token"].value()), data["token"])
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url + "?tab=reconcile")
        self.assertTrue(any("saved" in str(m) for m in get_messages(response.wsgi_request)))
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(MaterialReconciliation.objects.count(), 1)
        self.assertEqual(self.balance(), 90)

    def test_receipt_confirmation_post_replay_and_compact_pdf_controls(self):
        movement, _ = self.restore(1)
        data = {"action": "receipt", "token": str(uuid4()), "movements": [str(movement.pk)]}
        before = self.balance()
        self.assertContains(self.client.get(self.url), "Generate Bon de retour")
        self.assertRedirects(self.client.post(self.url, data), self.url + "?tab=returns")
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        response = self.client.get(self.url)
        self.assertEqual(ReturnReceipt.objects.count(), 1)
        self.assertContains(response, "View PDF")
        self.assertNotContains(response, 'id="pdf-language-')
        self.assertContains(response, "No undocumented physical returns are available.")
        self.assertNotContains(response, "renderer_version")
        self.assertEqual(self.balance(), before)

    def test_pdf_language_selection_failure_and_csrf(self):
        movement, _ = self.restore(1)
        receipt = self.receipt([movement])
        url = reverse("return_receipt_pdf", args=[receipt.pk])
        self.client.cookies["django_language"] = "fr"
        with patch("requests_app.material_outcome_views.generate_receipt_pdf", side_effect=ValidationError("Synthetic private error")) as generate:
            response = self.client.post(url, {"language": "fr"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(generate.call_args.args[2], "fr")
            self.assertNotContains(response, 'type="hidden" name="language"', status_code=503)
            self.assertNotContains(response, "Synthetic private error", status_code=503)
        with patch("requests_app.material_outcome_views.generate_receipt_pdf", side_effect=ValidationError("Synthetic")) as generate:
            self.assertEqual(self.client.post(url, {"language": "../secret"}).status_code, 503)
            self.assertEqual(generate.call_args.args[2], "fr")
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(url, {"language": "fr"}).status_code, 403)

    def test_many_materials_keep_accessible_individual_controls(self):
        req, item = self.make_request()
        for index in range(12):
            material = Material.objects.create(category=self.category, code=f"MANY{index}", name=f"Material {index}", stock_quantity=5, unit="pcs")
            RequestMaterialItem.objects.create(request=req, material=material, quantity=1)
        self.issue(req)
        response = self.client.get(reverse("material_outcomes", args=[req.pk]))
        self.assertEqual(len(response.context["material_rows"]), 13)
        self.assertContains(response, 'data-material-row ', count=13)
        self.assertContains(response, 'data-outcome="RETURNED"', count=13)

    def test_french_labels_and_authorization(self):
        self.client.cookies['django_language'] = "fr"
        response = self.client.get(self.url)
        for label in ("Gestion du matériel", "Vue d’ensemble", "Régulariser", "Retours et bons de retour", "Non encore régularisé"):
            self.assertContains(response, label)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"action": "receipt"}).status_code, 403)

    def test_user_text_is_escaped_in_rows_and_data_attributes(self):
        self.material.name = '<img src=x onerror=alert(1)>'
        self.material.save(update_fields=["name"])
        response = self.client.get(self.url)
        self.assertNotContains(response, self.material.name)
        self.assertContains(response, '&lt;img src=x onerror=alert(1)&gt;')

    def test_tab_fallback_and_exactly_one_server_selected_panel(self):
        import re
        for tab in ("overview", "reconcile", "returns", "unknown"):
            response = self.client.get(self.url, {"tab": tab})
            expected = tab if tab != "unknown" else "overview"
            self.assertEqual(response.context["active_tab"], expected)
            panels = re.findall(r'<div role="tabpanel" id="panel-([^"]+)"[^>]*>', response.content.decode())
            self.assertCountEqual(panels, ["overview", "reconcile", "returns"])
            for name in panels:
                tag = re.search(r'<div role="tabpanel" id="panel-' + name + r'"[^>]*>', response.content.decode()).group()
                self.assertEqual("hidden" in tag, name != expected)

    def test_inline_return_reuses_service_and_token_without_navigation_away(self):
        token = self.token()
        data = {"action": "return", "item": str(self.item.pk), "quantity": "2", "reason": "Unused", "operation_token": token}
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url + "?tab=returns")
        self.assertEqual(self.balance(), 92)
        self.assertRedirects(self.client.post(self.url, data), self.url + "?tab=returns")
        self.assertEqual(self.balance(), 92)
        self.assertEqual(StockMovement.objects.filter(movement_type="RETURN").count(), 1)
        view = self.client.get(self.url + "?tab=returns")
        self.assertContains(view, 'data-return-form')
        self.assertContains(view, 'max="8.00"')
        self.assertContains(view, "Generate Bon de retour")

    def test_inline_return_errors_permissions_csrf_and_full_return_replay(self):
        data = {"action": "return", "item": str(self.item.pk), "quantity": "11", "reason": "Unused", "operation_token": self.token()}
        response = self.client.post(self.url, data)
        self.assertEqual(response.context["active_tab"], "returns")
        self.assertContains(response, "remain available to return")
        self.assertEqual(self.balance(), 90)
        self.assertEqual(response.context['material_rows'][0]['return_form']['operation_token'].value(), data['operation_token'])
        invalid_item = self.client.post(self.url, dict(data, item="999999999"))
        self.assertContains(invalid_item, "Select a material from this request.")
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url, data).status_code, 403)
        data['quantity'] = '10'
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(self.balance(), 100)
        self.assertNotContains(self.client.get(self.url + "?tab=returns"), 'data-return-form')
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
