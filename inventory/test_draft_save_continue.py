"""Save redirects to a fresh form; continuing resolves the exact owned draft."""
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .entry_drafts import cancel_draft
from .models import MaterialEntryDraft
from .test_entry_drafts import DraftFixtures


class DraftSaveContinueTests(DraftFixtures, TestCase):
    def test_incomplete_saves_redirect_to_fresh_form_and_restore_every_value(self):
        before = self.snapshot()
        for mode in ("new", "existing"):
            data = self.payload(mode, name="Partially entered product", quantity="unfinished", received_on="",
                supplier="Private supplier", delivery_reference="Private reference", notes="Private notes",
                description="Private description", unit_price="19.00", is_active="")
            response, draft = self.save(data)
            query = parse_qs(urlsplit(response.url).query)
            self.assertEqual(query, {"mode": [mode], "saved_draft": [str(draft.pk)]})
            self.assertFalse(list(get_messages(response.wsgi_request)))
            for private in ("Private", "Partially", "unfinished"):
                self.assertNotIn(private, response.url)
            fresh = self.client.get(response.url)
            self.assertIsNone(fresh.context["draft"])
            self.assertFalse(fresh.context["receipt_form"].is_bound)
            self.assertIsNone(fresh.context["receipt_form"]["quantity"].value())
            self.assertNotEqual(fresh.context["receipt_form"]["token"].value(), draft.signed_token)
            self.assertEqual(fresh.context["saved_draft"].pk, draft.pk)
            self.assertContains(fresh, "Continue Editing")
            self.assertNotContains(fresh, "Private notes")
            self.assertNotContains(fresh, "Private reference")
            if mode == "existing":
                self.assertIsNone(fresh.context["receipt_form"]["material"].value())
                self.assertContains(fresh, self.material.name)
            else:
                self.assertIsNone(fresh.context["material_form"]["name"].value())
                self.assertContains(fresh, "Partially entered product")
            resumed = self.client.get(fresh.context["saved_draft_url"])
            self.assertEqual(resumed.context["draft"].pk, draft.pk)
            self.assertEqual(resumed.context["mode"], mode)
            self.assertEqual(resumed.context["draft_version"], draft.version)
            for field in ("quantity", "received_on", "supplier", "delivery_reference", "notes"):
                self.assertEqual(resumed.context["receipt_form"][field].value(), data[field])
            if mode == "existing":
                self.assertEqual(str(resumed.context["receipt_form"]["material"].value()), str(self.material.pk))
                self.assertEqual(resumed.context["current_stock"], 10)
            else:
                for field in ("name", "description", "unit_price"):
                    self.assertEqual(resumed.context["material_form"][field].value(), data[field])
                self.assertFalse(resumed.context["material_form"]["is_active"].value())
            self.assertEqual(self.snapshot(), before)

    def test_continue_uses_exact_id_even_after_another_draft_is_saved(self):
        first_response, first = self.save(self.payload(name="First product"))
        self.save(self.payload(name="Latest product"))
        page = self.client.get(first_response.url)
        target = page.context["saved_draft_url"]
        self.assertEqual(parse_qs(urlsplit(target).query), {"mode": ["new"], "draft": [str(first.pk)]})
        self.assertEqual(self.client.get(target).context["material_form"]["name"].value(), "First product")
        self.assertEqual(MaterialEntryDraft.objects.count(), 2)

    def test_resumed_save_updates_same_draft_and_continue_loads_current_version(self):
        data = self.payload("existing", quantity="5")
        response, draft = self.save(data)
        original_notification_url = response.url
        update = {**data, "draft_id": draft.pk, "version": 1, "quantity": "10", "notes": "Changed"}
        updated_response, updated = self.save(update)
        self.assertEqual(updated.pk, draft.pk)
        self.assertEqual(MaterialEntryDraft.objects.count(), 1)
        self.save(update)  # Lost-response retry cannot create another draft/version.
        for url in (original_notification_url, updated_response.url):
            notification = self.client.get(url)
            resumed = self.client.get(notification.context["saved_draft_url"])
            self.assertEqual(resumed.context["draft_version"], 2)
            self.assertEqual(resumed.context["receipt_form"]["quantity"].value(), "10")

    def test_inaccessible_notification_cannot_disclose_or_resume_draft(self):
        response, draft = self.save(self.payload(name="Owner-only material"))
        page = self.client.get(response.url)
        resume_url = page.context["saved_draft_url"]
        other = get_user_model().objects.create_user(username="different-draft-owner", can_manage_stock=True)
        self.client.force_login(other)
        page = self.client.get(response.url)
        self.assertIsNone(page.context["saved_draft"])
        self.assertNotContains(page, "Owner-only material")
        self.assertEqual(self.client.get(resume_url).status_code, 404)

    def test_cancelled_completed_and_invalid_notifications_are_not_actionable(self):
        for mode in ("new", "existing"):
            data = self.payload(mode)
            response, draft = self.save(data)
            resume_url = self.client.get(response.url).context["saved_draft_url"]
            if mode == "new":
                cancel_draft(user=self.user, draft_id=draft.pk, version=1)
            else:
                confirm = self.reviewed(draft, data)
                self.assertEqual(self.client.post(reverse("material_entries"), confirm).status_code, 302)
            page = self.client.get(response.url)
            self.assertIsNone(page.context["saved_draft"])
            self.assertEqual(self.client.get(resume_url).status_code, 404)
        for key in ("bad-id", "999999999"):
            page = self.client.get(reverse("material_entries") + f"?saved_draft={key}")
            self.assertEqual(page.status_code, 200)
            self.assertIsNone(page.context["saved_draft"])

    def test_failed_save_keeps_entered_values_and_original_version(self):
        data = self.payload(name="Original")
        _, draft = self.save(data)
        self.save({**data, "draft_id": draft.pk, "version": 1, "name": "Newer"})
        response = self.client.post(reverse("material_entries"), {**data, "action": "save_draft",
            "draft_id": draft.pk, "version": 1, "name": "Unsaved stale edit", "quantity": "partial"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["saved_draft"])
        self.assertEqual(response.context["material_form"]["name"].value(), "Unsaved stale edit")
        self.assertEqual(response.context["receipt_form"]["quantity"].value(), "partial")
        self.assertEqual(response.context["draft_version"], "1")
        draft.refresh_from_db()
        self.assertEqual(draft.data["material"]["name"], "Newer")

    def test_notification_is_translated_dismissible_and_escapes_material_name(self):
        response, draft = self.save(self.payload(name='<img src=x onerror="alert(1)">'))
        for language, title, action, dismiss in (
                ("fr", "Brouillon enregistré avec succès", "Continuer la modification", "Fermer la notification"),
                ("en", "Draft saved successfully", "Continue Editing", "Dismiss notification")):
            self.client.cookies["django_language"] = language
            page = self.client.get(response.url)
            for text in (title, action, dismiss):
                self.assertContains(page, text)
            self.assertContains(page, 'role="status"')
            self.assertContains(page, 'data-entry-dismiss')
            self.assertNotContains(page, '<img src=x onerror="alert(1)">')
            self.assertContains(page, '&lt;img')
