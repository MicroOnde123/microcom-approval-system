from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Department


DRC_MATCH_MESSAGE_EN = "All behind the Leopards — DR Congo vs England"
DRC_MATCH_MESSAGE_FR = "Tous derrière les Léopards — RDC vs Angleterre"


class DRCMatchBannerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        department = Department.objects.create(
            name="DRC Banner Department",
            code="DRC-BANNER",
        )
        cls.user = get_user_model().objects.create_user(
            username="drc-match-user",
            password="pass12345",
            email="drc-match@example.com",
            full_name="DRC Match User",
            department=department,
            can_manage_stock=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def normal_page_urls(self):
        return {
            "dashboard": reverse("dashboard"),
            "create_request": reverse("create_request"),
            "my_requests": reverse("my_requests"),
            "pending_approvals": reverse("pending_approvals"),
            "approval_history": reverse("approval_history"),
            "material_reports": reverse("material_reports"),
        }

    @override_settings(SHOW_DRC_MATCH_BANNER=False)
    def test_disabled_hides_all_football_campaign_elements(self):
        for page_name, url in self.normal_page_urls().items():
            with self.subTest(page=page_name):
                response = self.client.get(url, HTTP_HOST="127.0.0.1")
                html = response.content.decode()

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("drc-match-", html)
                self.assertNotIn(DRC_MATCH_MESSAGE_EN, html)
                self.assertNotIn("images/leopard_mascot.jfif", html)
                self.assertNotIn("images/microcom_logo.png", html)

    @override_settings(SHOW_DRC_MATCH_BANNER=True)
    def test_enabled_shows_banner_ribbon_and_mascot_on_expected_pages(self):
        for page_name, url in self.normal_page_urls().items():
            with self.subTest(page=page_name):
                response = self.client.get(url, HTTP_HOST="127.0.0.1")
                html = response.content.decode()

                self.assertEqual(response.status_code, 200)
                self.assertIn('<div class="drc-match-ribbon"', html)
                self.assertIn('<aside class="drc-match-mascot"', html)
                self.assertIn(DRC_MATCH_MESSAGE_EN, html)
                self.assertIn("/static/images/leopard_mascot.jfif", html)

                if page_name == "dashboard":
                    self.assertIn('<section class="drc-match-banner"', html)
                    self.assertIn("/static/images/microcom_logo.png", html)
                else:
                    self.assertNotIn('<section class="drc-match-banner"', html)

    @override_settings(SHOW_DRC_MATCH_BANNER=True)
    def test_enabled_uses_french_match_text_only(self):
        response = self.client.get(
            reverse("dashboard"),
            HTTP_ACCEPT_LANGUAGE="fr",
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, DRC_MATCH_MESSAGE_FR, count=4)

    def test_required_images_and_static_template_paths_exist(self):
        self.assertIsNotNone(finders.find("images/leopard_mascot.jfif"))
        self.assertIsNotNone(finders.find("images/microcom_logo.png"))

        mascot_template = (
            settings.BASE_DIR / "templates/includes/drc_match_mascot.html"
        ).read_text(encoding="utf-8")
        banner_template = (
            settings.BASE_DIR / "templates/includes/drc_match_banner.html"
        ).read_text(encoding="utf-8")

        self.assertIn("{% load i18n static %}", mascot_template)
        self.assertIn("{% static 'images/leopard_mascot.jfif' %}", mascot_template)
        self.assertIn("{% load i18n static %}", banner_template)
        self.assertIn("{% static 'images/microcom_logo.png' %}", banner_template)

    def test_print_templates_do_not_use_football_campaign_elements(self):
        print_templates = [
            "templates/requests_app/approved_document.html",
            "templates/requests_app/permission_document.html",
            "templates/requests_app/bulk_print_material_documents.html",
        ]

        for template_path in print_templates:
            with self.subTest(template=template_path):
                template_source = (settings.BASE_DIR / template_path).read_text(
                    encoding="utf-8"
                )

                self.assertNotIn("base.html", template_source)
                self.assertNotIn("drc-match-banner", template_source)
                self.assertNotIn("drc-match-ribbon", template_source)
                self.assertNotIn("drc-match-mascot", template_source)
