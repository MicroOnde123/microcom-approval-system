from html import unescape

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .approval_forms import ApprovalActionForm
from .models import StockMovement
from .test_stock_safety import StockSafetyFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ApprovalLocalizationTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.approval = self.req.approvals.get()
        self.url = reverse("approval_detail", args=[self.approval.pk])

    def language(self, language):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language

    def assert_choices(self, language, labels, comment):
        self.language(language)
        response = self.client.get(self.url, HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Language"], language)
        body = unescape(response.content.decode("utf-8"))
        for value, label in zip(("APPROVE", "REJECT", "RETURN"), labels):
            self.assertIn(f'value="{value}">{label}</option>', body)
        self.assertIn(comment, body)
        self.assertNotIn("\ufffd", body)

    def test_english_action_choices(self):
        self.assert_choices("en", ("Approve", "Reject", "Return for changes"), "Comment")

    def test_french_action_choices(self):
        self.assert_choices("fr", ("Approuver", "Rejeter", "Retourner pour correction"), "Commentaire")

    def test_internal_action_values_are_unchanged_in_both_languages(self):
        for language in ("en", "fr"):
            with override(language):
                for value in ("APPROVE", "REJECT", "RETURN"):
                    with self.subTest(language=language, value=value):
                        form = ApprovalActionForm({"action": value, "comment": "Synthetic comment"})
                        self.assertTrue(form.is_valid())
                        self.assertEqual(form.cleaned_data["action"], value)
                self.assertFalse(ApprovalActionForm({"action": "Approuver"}).is_valid())

    def assert_action(self, language, action, message, status):
        self.language(language)
        response = self.client.post(self.url, {"action": action, "comment": "Synthetic comment"},
                                    follow=True, HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Language"], language)
        self.assertIn(message, [str(item) for item in response.context["messages"]])
        self.req.refresh_from_db()
        self.approval.refresh_from_db()
        self.assertEqual(self.req.status, status)
        self.assertEqual(self.approval.status, status)
        self.assertEqual(self.approval.acted_by_id, self.user.pk)
        approved = action == "APPROVE"
        self.assertEqual(self.req.stock_deducted, approved)
        self.assertEqual(self.balance(), 90 if approved else 100)
        self.assertEqual(StockMovement.objects.filter(request=self.req, movement_type="OUT").count(), int(approved))

    def test_approval_success_english(self):
        self.assert_action("en", "APPROVE", "Request approved successfully.", "APPROVED")

    def test_approval_success_french(self):
        self.assert_action("fr", "APPROVE", "Demande approuvée avec succès.", "APPROVED")

    def test_rejection_success_english(self):
        self.assert_action("en", "REJECT", "Request rejected successfully.", "REJECTED")

    def test_rejection_success_french(self):
        self.assert_action("fr", "REJECT", "Demande rejetée avec succès.", "REJECTED")

    def test_return_for_correction_english(self):
        self.assert_action("en", "RETURN", "Request returned for changes.", "RETURNED")

    def test_return_for_correction_french(self):
        self.assert_action("fr", "RETURN", "Demande retournée pour correction.", "RETURNED")

    def test_inactive_approval_messages(self):
        self.assert_action("en", "APPROVE", "Request approved successfully.", "APPROVED")
        for language, message in (("en", "This approval is no longer active."),
                                  ("fr", "Cette approbation n'est plus active.")):
            with self.subTest(language=language):
                self.language(language)
                response = self.client.get(self.url, follow=True, HTTP_HOST="127.0.0.1")
                self.assertIn(message, [str(item) for item in response.context["messages"]])
        self.assertEqual(self.balance(), 90)

    def test_existing_language_cookie_takes_precedence_over_accept_language(self):
        self.language("fr")
        response = self.client.get(self.url, HTTP_HOST="127.0.0.1", HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual(response.headers["Content-Language"], "fr")
        self.assertContains(response, "Retourner pour correction")
