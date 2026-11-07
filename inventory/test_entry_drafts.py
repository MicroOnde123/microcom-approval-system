"""Owned independent draft lifecycle; synthetic local PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from html.parser import HTMLParser
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.translation import activate, deactivate

from .entry_drafts import create_draft, update_draft, cancel_draft, complete_draft
from .entry_review import service_arguments, sign_review
from .entry_forms import ReceiptForm, ExistingReceiptForm, NewMaterialForm
from .entry_services import new_token, receive_stock
from .pricing import price_state, update_price
from .models import Material, MaterialReceipt, MaterialReceiptLine, MaterialEntryDraft, MaterialPriceChange
from .test_material_entries import Fixtures
from requests_app.models import StockMovement
from invoicing.models import Invoice


class DraftFixtures(Fixtures):
    def setUp(self):
        activate("en")
        self.addCleanup(deactivate)
        super().setUp()
        self.client.force_login(self.user)

    def payload(self, mode="new", **extra):
        return {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}),
                "mode": mode, "token": new_token(self.user, mode), **extra}

    def save(self, payload):
        response = self.client.post(reverse("material_entries"), {**payload, "action": "save_draft"})
        self.assertEqual(response.status_code, 302, response.content.decode()[-1000:])
        return response, MaterialEntryDraft.objects.get(signed_token=payload["token"])

    def snapshot(self):
        return [list(model.objects.order_by("pk").values()) for model in
                (Material, MaterialReceipt, MaterialReceiptLine, StockMovement, MaterialPriceChange, Invoice)]

    def resume_url(self, draft):
        return reverse("material_entries") + f"?draft={draft.pk}"

    def reviewed(self, draft, payload):
        posted = {**payload, "draft_id": draft.pk, "version": draft.version, "action": "verify"}
        response = self.client.post(reverse("material_entries"), posted)
        self.assertTrue(response.context["review"], response.content.decode()[-1500:])
        return {**posted, "action": "confirm", "review_proof": response.context["review_proof"]}


class EntryDraftTests(DraftFixtures, TestCase):
    def test_incomplete_drafts_in_both_modes_preserve_invalid_values_without_inventory_writes(self):
        before = self.snapshot()
        for mode in ("new", "existing"):
            data = {"mode": mode, "token": new_token(self.user, mode), "quantity": "unfinished",
                    "received_on": "31/02/2026", "notes": "Continue later", "unit_price": "987.65", "currency": "EUR"}
            response, draft = self.save(data)
            restored = self.client.get(self.resume_url(draft))
            self.assertEqual(restored.context["receipt_form"]["quantity"].value(), "unfinished")
            self.assertEqual(restored.context["receipt_form"]["received_on"].value(), "31/02/2026")
            self.assertFalse(restored.context["receipt_form"].errors)
            self.assertEqual(draft.mode, mode)
            self.assertEqual(self.snapshot(), before)

    def test_independent_drafts_new_entry_and_resume_restore_correct_values(self):
        first_response, first = self.save(self.payload(name="First product", quantity="7"))
        second_response, second = self.save(self.payload(name="Second product", quantity="9"))
        _, existing = self.save(self.payload("existing", notes="Existing draft"))
        self.assertEqual(MaterialEntryDraft.objects.count(), 3)
        first_page = self.client.get(self.resume_url(first))
        self.assertEqual(first_page.context["material_form"]["name"].value(), "First product")
        self.assertEqual(first_page.context["receipt_form"]["quantity"].value(), "7")
        self.assertEqual(self.client.get(self.resume_url(second)).context["material_form"]["name"].value(), "Second product")
        self.assertContains(first_page, "Cable (CAB)")
        self.assertContains(first_page, "First product")
        self.assertContains(first_page, "Second product")
        fresh = self.client.get(reverse("material_entries") + "?mode=new")
        self.assertIsNone(fresh.context["draft"])
        self.assertNotEqual(fresh.context["receipt_form"]["token"].value(), first.signed_token)
        self.assertFalse(MaterialReceipt.objects.exists())

    def test_update_and_identical_retries_do_not_create_duplicate_drafts(self):
        data = self.payload()
        _, draft = self.save(data)
        self.save(data)
        self.assertEqual(MaterialEntryDraft.objects.count(), 1)
        update = {**data, "draft_id": draft.pk, "version": draft.version, "name": "Updated product"}
        self.save(update)
        self.save(update)
        draft.refresh_from_db()
        self.assertEqual((draft.version, draft.data["material"]["name"]), (2, "Updated product"))
        self.assertEqual(MaterialEntryDraft.objects.count(), 1)

    def test_reused_creation_token_cannot_overwrite_a_different_draft_payload(self):
        data = self.payload(name="Original")
        self.save(data)
        response = self.client.post(reverse("material_entries"), {**data, "name": "Changed", "action": "save_draft"})
        self.assertContains(response, "Resume it before saving changes.")
        self.assertEqual(MaterialEntryDraft.objects.get().data["material"]["name"], "Original")

    def test_stale_tab_keeps_old_version_and_cannot_overwrite_newer_saved_values(self):
        data = self.payload()
        _, draft = self.save(data)
        self.save({**data, "draft_id": draft.pk, "version": 1, "name": "Newer"})
        stale = {**data, "draft_id": draft.pk, "version": 1, "name": "Stale", "action": "save_draft"}
        for _ in range(2):
            response = self.client.post(reverse("material_entries"), stale)
            self.assertContains(response, "Reload it before saving again.")
            self.assertContains(response, 'name="version" value="1"')
            self.assertEqual(response.context["material_form"]["name"].value(), "Stale")
        draft.refresh_from_db()
        self.assertEqual((draft.version, draft.data["material"]["name"]), (2, "Newer"))

    def test_cancel_is_confirmed_versioned_soft_and_idempotent(self):
        _, first = self.save(self.payload(name="Cancel this"))
        _, second = self.save(self.payload(name="Keep this"))
        before = self.snapshot()
        url = reverse("cancel_material_entry_draft", args=[first.pk])
        self.assertContains(self.client.get(url), "Confirm draft cancellation")
        first.refresh_from_db()
        self.assertEqual(first.status, "DRAFT")
        self.assertEqual(self.client.post(url, {"version": 1}).status_code, 409)
        for _ in range(2):
            self.assertEqual(self.client.post(url, {"version": 1, "confirm_cancel": "yes"}).status_code, 302)
        first.refresh_from_db()
        self.assertEqual((first.status, first.version), ("CANCELLED", 2))
        self.assertEqual(first.data["material"]["name"], "Cancel this")
        page = self.client.get(reverse("material_entries"))
        self.assertNotContains(page, "Cancel this")
        self.assertContains(page, "Keep this")
        self.assertEqual(self.snapshot(), before)
        second.refresh_from_db()
        self.assertEqual(second.status, "DRAFT")

    def test_stale_cancellation_does_not_cancel_updated_draft(self):
        data = self.payload()
        _, draft = self.save(data)
        self.save({**data, "draft_id": draft.pk, "version": 1, "notes": "newer"})
        response = self.client.post(reverse("cancel_material_entry_draft", args=[draft.pk]),
                                    {"version": 1, "confirm_cancel": "yes"})
        self.assertEqual(response.status_code, 409)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "DRAFT")

    def test_owner_permissions_csrf_and_missing_references(self):
        _, draft = self.save(self.payload())
        cancel_url = reverse("cancel_material_entry_draft", args=[draft.pk])
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(cancel_url, {"version": 1, "confirm_cancel": "yes"}).status_code, 403)
        other = get_user_model().objects.create_user(username="other-draft", can_manage_stock=True, is_superuser=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("material_entries") + f"?draft={draft.pk}").status_code, 404)
        self.assertEqual(self.client.get(cancel_url).status_code, 404)
        self.assertEqual(self.client.post(cancel_url, {"version": 1, "confirm_cancel": "yes"}).status_code, 404)
        with self.assertRaises(ValidationError):
            cancel_draft(user=other, draft_id=draft.pk, version=1)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            update_draft(user=self.user, draft_id=draft.pk, version=1, data={})

    def test_review_modify_and_confirmation_retry_in_both_modes(self):
        for mode in ("new", "existing"):
            data = self.payload(mode)
            _, draft = self.save(data)
            before = self.snapshot()
            confirm = self.reviewed(draft, data)
            modified = self.client.post(reverse("material_entries"), {**confirm, "action": "modify"})
            self.assertFalse(modified.context["review"])
            self.assertEqual(str(modified.context["receipt_form"]["quantity"].value()), data["quantity"])
            self.assertEqual(self.snapshot(), before)
            first = self.client.post(reverse("material_entries"), confirm)
            self.assertEqual(first.status_code, 302)
            after = self.snapshot()
            second = self.client.post(reverse("material_entries"), confirm)
            self.assertEqual(second.status_code, 302)
            self.assertEqual(second.url, first.url)
            self.assertEqual(self.snapshot(), after)
            altered = self.client.post(reverse("material_entries"), {**confirm, "quantity": "99"})
            self.assertEqual(altered.status_code, 200)
            self.assertEqual(self.snapshot(), after)
            draft.refresh_from_db()
            self.assertEqual((draft.status, draft.version), ("COMPLETED", 2))
            cancel_draft_url = reverse("cancel_material_entry_draft", args=[draft.pk])
            self.assertEqual(self.client.post(cancel_draft_url, {"version": 2, "confirm_cancel": "yes"}).status_code, 409)
            self.assertEqual(self.client.get(reverse("material_entries") + f"?draft={draft.pk}").status_code, 404)

    def test_changed_tampered_or_stale_confirmation_does_not_change_stock(self):
        data = self.payload("existing")
        _, draft = self.save(data)
        confirm = self.reviewed(draft, data)
        before = self.snapshot()
        for change in ({"quantity": "99"}, {"review_proof": "tampered"}, {"token": new_token(self.user,"existing")}):
            response = self.client.post(reverse("material_entries"), {**confirm, **change})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.snapshot(), before)
        self.save({**data, "draft_id": draft.pk, "version": 1, "notes": "newer"})
        response = self.client.post(reverse("material_entries"), confirm)
        self.assertContains(response, "Reload it before continuing.")
        # Even a manually substituted version cannot reuse the earlier proof.
        response = self.client.post(reverse("material_entries"), {**confirm, "version": 2})
        self.assertContains(response, "The reviewed details have changed")
        self.assertEqual(self.snapshot(), before)

    def test_cancelled_or_saved_operation_cannot_bypass_draft_via_direct_receipt(self):
        data = self.payload("existing")
        _, draft = self.save(data)
        args = dict(user=self.user, mode="existing", token=data["token"], material_id=self.material.pk, receipt_data=self.data)
        with self.assertRaises(ValidationError):
            receive_stock(**args)
        cancel_draft(user=self.user, draft_id=draft.pk, version=1)
        with self.assertRaises(ValidationError):
            receive_stock(**args)
        self.assertFalse(MaterialReceipt.objects.exists())

    def test_cancelled_missing_and_invalid_references_are_not_resumed(self):
        _, draft = self.save(self.payload())
        cancel_draft(user=self.user, draft_id=draft.pk, version=1)
        for key in (draft.pk, "missing", "999999999"):
            self.assertEqual(self.client.get(reverse("material_entries") + f"?draft={key}").status_code, 404)

    def test_confirmation_failure_rolls_back_receipt_and_leaves_draft_resumable(self):
        data = self.payload("existing")
        _, draft = self.save(data)
        confirm = self.reviewed(draft, data)
        before = self.snapshot()
        with patch("inventory.entry_services.StockMovement.objects.create", side_effect=RuntimeError("Synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("material_entries"), confirm)
        self.assertEqual(self.snapshot(), before)
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.version, draft.receipt_id), ("DRAFT", 1, None))
        self.assertEqual(self.client.post(reverse("material_entries"), confirm).status_code, 302)

    def test_pagination_and_actual_french_english_controls(self):
        for i in range(12):
            self.save(self.payload(name=f"Draft product {i}"))
        response = self.client.get(reverse("material_entries"))
        self.assertEqual(len(response.context["saved_drafts"]), 10)
        self.assertEqual(len(self.client.get(reverse("material_entries") + "?draft_page=2").context["saved_drafts"]), 2)
        draft = MaterialEntryDraft.objects.first()
        for language, labels in (("fr", ["Brouillons enregistrés", "Nouvelle entrée", "Enregistrer le brouillon", "Annuler le brouillon"]),
                                 ("en", ["Saved Drafts", "New Entry", "Save Draft", "Cancel Draft"])):
            self.client.cookies["django_language"] = language
            page = self.client.get(reverse("material_entries") + f"?draft={draft.pk}")
            for label in labels:
                self.assertContains(page, label)
            if language == "fr":
                self.assertNotContains(page, "You can save an unfinished entry")
                self.assertContains(self.client.get(reverse("cancel_material_entry_draft", args=[draft.pk])), "Confirmer l’annulation")

    def test_material_and_category_forms_are_not_nested(self):
        class Forms(HTMLParser):
            depth = 0
            nested = False
            def handle_starttag(self, tag, attrs):
                if tag == "form":
                    self.nested = self.nested or self.depth > 0
                    self.depth += 1
            def handle_endtag(self, tag):
                if tag == "form":
                    self.depth -= 1
        parser = Forms()
        parser.feed(self.client.get(reverse("material_entries")).content.decode())
        self.assertFalse(parser.nested)
        self.assertEqual(parser.depth, 0)


class ExistingMaterialDraftTests(DraftFixtures, TestCase):
    def test_same_material_drafts_restore_all_values_and_edit_independently(self):
        before = self.snapshot()
        first_data = self.payload("existing", quantity="5", supplier="Supplier A", delivery_reference="REF-A", notes="First delivery")
        second_data = self.payload("existing", quantity="10", supplier="Supplier B", received_on="", delivery_reference="REF-B", notes="Second delivery")
        first_url, first = self.save(first_data)
        second_url, second = self.save(second_data)
        self.save(self.payload(name="Router MikroTik"))
        self.assertNotEqual(first.operation_token, second.operation_token)
        for saved_draft, data in ((first, first_data), (second, second_data)):
            page = self.client.get(self.resume_url(saved_draft))
            form = page.context["receipt_form"]
            for field in ("material", "quantity", "supplier", "received_on", "delivery_reference", "notes"):
                self.assertEqual(str(form[field].value()), str(data[field]))
            self.assertFalse(form.errors)
        self.save({**second_data, "draft_id": second.pk, "version": 1, "notes": "Updated second delivery"})
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((first.version, first.data["notes"]), (1, "First delivery"))
        self.assertEqual((second.version, second.data["notes"]), (2, "Updated second delivery"))
        fresh = self.client.get(reverse("material_entries") + "?mode=existing")
        self.assertIsNone(fresh.context["draft"])
        self.assertNotIn(fresh.context["receipt_form"]["token"].value(), [first.signed_token, second.signed_token])
        for language, mode_label in (("en", "Existing Material Receipt"), ("fr", "Réception de matériel existant")):
            self.client.cookies["django_language"] = language
            page = self.client.get(reverse("material_entries"))
            self.assertContains(page, mode_label, count=2)
            self.assertContains(page, "Cable (CAB) — 5 m")
            self.assertContains(page, "Cable (CAB) — 10 m")
            self.assertContains(page, "Router MikroTik")
        self.assertEqual(MaterialEntryDraft.objects.count(), 3)
        self.assertEqual(self.snapshot(), before)

    def test_confirm_one_and_cancel_other_does_not_consume_or_change_confirmed_receipt(self):
        first_data, second_data = self.payload("existing", quantity="5"), self.payload("existing", quantity="10")
        _, first = self.save(first_data)
        _, second = self.save(second_data)
        second_values = second.data.copy()
        confirm = self.reviewed(first, first_data)
        for _ in range(2):
            self.assertEqual(self.client.post(reverse("material_entries"), confirm).status_code, 302)
        self.material.refresh_from_db(); first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 15)
        self.assertEqual((second.status, second.version, second.receipt_id, second.data), ("DRAFT", 1, None, second_values))
        self.assertEqual(MaterialReceipt.objects.count(), 1)
        after_confirmation = self.snapshot()
        cancel = reverse("cancel_material_entry_draft", args=[second.pk])
        for _ in range(2):
            self.assertEqual(self.client.post(cancel, {"version": 1, "confirm_cancel": "yes"}).status_code, 302)
        self.assertEqual(self.snapshot(), after_confirmation)
        self.assertTrue(MaterialReceipt.objects.filter(pk=first.receipt_id).exists())
        self.assertEqual(StockMovement.objects.filter(movement_type="IN").count(), 1)

    def test_two_receipts_for_same_material_finalize_separately_once_each(self):
        first_data, second_data = self.payload("existing", quantity="5"), self.payload("existing", quantity="10")
        _, first = self.save(first_data)
        _, second = self.save(second_data)
        first_confirm = self.reviewed(first, first_data)
        second_confirm = self.reviewed(second, second_data)
        for confirm in (first_confirm, first_confirm, second_confirm, second_confirm):
            self.assertEqual(self.client.post(reverse("material_entries"), confirm).status_code, 302)
        self.material.refresh_from_db(); first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 25)
        self.assertNotEqual(first.receipt_id, second.receipt_id)
        self.assertEqual(MaterialReceipt.objects.count(), 2)
        self.assertEqual(StockMovement.objects.filter(movement_type="IN").count(), 2)
        self.assertEqual(MaterialReceiptLine.objects.get(receipt_id=first.receipt_id).stock_after, 15)
        self.assertEqual(MaterialReceiptLine.objects.get(receipt_id=second.receipt_id).stock_after, 25)

    def test_resume_uses_live_stock_and_price_and_confirm_preserves_later_catalogue_changes(self):
        data = self.payload("existing", quantity="5")
        resume, draft = self.save(data)
        actor = get_user_model().objects.create_superuser(username="catalogue-editor", password="synthetic")
        receive_stock(user=self.user, mode="existing", token=new_token(self.user, "existing"),
                      material_id=self.material.pk, receipt_data={**self.data, "quantity": "3"})
        self.material.refresh_from_db()
        self.material = update_price(self.material.pk, actor, price=Decimal("7.50"), currency="EUR",
            reason="Current catalogue price", expected_state=price_state(self.material))
        before_resume = self.snapshot()
        page = self.client.get(self.resume_url(draft))
        self.assertEqual(page.context["current_stock"], 13)
        self.assertEqual(page.context["estimated_stock"], 18)
        self.assertContains(page, "7.50 EUR")
        self.assertEqual(self.snapshot(), before_resume)
        confirm = self.reviewed(draft, data)
        receive_stock(user=self.user, mode="existing", token=new_token(self.user, "existing"),
                      material_id=self.material.pk, receipt_data={**self.data, "quantity": "2"})
        self.material.refresh_from_db()
        self.material = update_price(self.material.pk, actor, price=Decimal("8.00"), currency="USD",
            reason="Later catalogue change", expected_state=price_state(self.material))
        ledger = list(MaterialPriceChange.objects.values())
        self.assertEqual(self.client.post(reverse("material_entries"), confirm).status_code, 302)
        self.material.refresh_from_db(); draft.refresh_from_db()
        self.assertEqual((self.material.stock_quantity, self.material.unit_price, self.material.currency), (20, Decimal("8"), "USD"))
        line = MaterialReceiptLine.objects.get(receipt_id=draft.receipt_id)
        self.assertEqual(line.stock_after, 20)
        self.assertEqual(line.material_snapshot["unit_price"], "8.00")
        self.assertEqual(list(MaterialPriceChange.objects.values()), ledger)

    def test_deleted_material_is_revalidated_before_draft_confirmation(self):
        data = self.payload("existing", quantity="5")
        _, draft = self.save(data)
        confirm = self.reviewed(draft, data)
        self.material.delete()
        before = self.snapshot()
        page = self.client.post(reverse("material_entries"), confirm)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["receipt_form"].errors)
        self.assertEqual(self.snapshot(), before)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "DRAFT")

    def test_revoked_stock_permission_blocks_resume_and_confirmation(self):
        data = self.payload("existing", quantity="5")
        resume, draft = self.save(data)
        confirm = self.reviewed(draft, data)
        self.user.can_manage_stock = False
        self.user.save(update_fields=["can_manage_stock"])
        before = self.snapshot()
        self.assertEqual(self.client.get(resume.url).status_code, 403)
        self.assertEqual(self.client.post(reverse("material_entries"), confirm).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "DRAFT")


class ConcurrentDraftTests(DraftFixtures, TransactionTestCase):
    def parallel(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=15)
                try:
                    return operation(user)
                except ValidationError:
                    return "conflict"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations))

    def test_concurrent_initial_save_has_one_persistent_draft(self):
        token = new_token(self.user, "new")
        results = self.parallel([lambda u: create_draft(user=u, mode="new", token=token, data={"material": {}}).pk] * 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(MaterialEntryDraft.objects.count(), 1)

    def test_concurrent_updates_have_one_winner(self):
        draft = create_draft(user=self.user, mode="new", token=new_token(self.user, "new"), data={"material": {}})
        results = self.parallel([lambda u: update_draft(user=u, draft_id=draft.pk, version=1, data={"material": {"name":"First"}}).version,
                                 lambda u: update_draft(user=u, draft_id=draft.pk, version=1, data={"material": {"name":"Second"}}).version])
        self.assertCountEqual(results, [2, "conflict"])

    def test_concurrent_confirmations_and_cancellation_preserve_correct_stock(self):
        data = self.payload("existing")
        _, draft = self.save(data)
        form = ExistingReceiptForm(data)
        self.assertTrue(form.is_valid())
        args = service_arguments(self.user, "existing", form, None)
        proof = sign_review(args, draft_context={"id":draft.pk,"version":1})
        def confirm(user):
            arguments = {**args,"user":user}
            return complete_draft(user=user,draft_id=draft.pk,version=1,arguments=arguments,review_proof=proof)[0].pk
        results = self.parallel([confirm, confirm])
        self.assertEqual(results[0], results[1])
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 12.5)
        self.assertEqual(StockMovement.objects.filter(movement_type="IN").count(), 1)
        # A fresh draft may be cancelled or finalized, but never both.
        data = self.payload("existing")
        _, draft = self.save(data)
        form = ExistingReceiptForm(data); self.assertTrue(form.is_valid())
        args = service_arguments(self.user,"existing",form,None)
        proof = sign_review(args,draft_context={"id":draft.pk,"version":1})
        results = self.parallel([confirm, lambda u: cancel_draft(user=u,draft_id=draft.pk,version=1)[0].status])
        self.assertIn("conflict",results)
        draft.refresh_from_db(); self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 15 if draft.status=="COMPLETED" else 12.5)
