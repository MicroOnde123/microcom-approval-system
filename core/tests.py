from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


INDEPENDENCE_MESSAGE_EN = "Happy Congolese Independence Day — June 30, 2026"
INDEPENDENCE_MESSAGE_FR = "Bonne fête de l’Indépendance de la RDC — 30 juin 2026"


class IndependenceBannerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="independence-user",
            password="pass12345",
            email="independence@example.com",
            full_name="Independence User",
        )

    def setUp(self):
        self.client.force_login(self.user)

    @override_settings(SHOW_INDEPENDENCE_BANNER=False)
    def test_disabled_hides_dashboard_banner_and_page_ribbon(self):
        dashboard_response = self.client.get(
            reverse("dashboard"),
            HTTP_HOST="127.0.0.1",
        )
        requests_response = self.client.get(
            reverse("my_requests"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(dashboard_response, 'class="independence-banner"')
        self.assertNotContains(dashboard_response, 'class="independence-ribbon"')
        self.assertNotContains(requests_response, 'class="independence-ribbon"')

    @override_settings(SHOW_INDEPENDENCE_BANNER=True)
    def test_enabled_shows_dashboard_banner_and_normal_page_ribbon(self):
        dashboard_response = self.client.get(
            reverse("dashboard"),
            HTTP_HOST="127.0.0.1",
        )
        requests_response = self.client.get(
            reverse("my_requests"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(dashboard_response, 'class="independence-banner"')
        self.assertContains(dashboard_response, 'class="independence-ribbon"')
        self.assertContains(dashboard_response, INDEPENDENCE_MESSAGE_EN, count=2)
        self.assertContains(requests_response, 'class="independence-ribbon"')
        self.assertNotContains(requests_response, 'class="independence-banner"')

    @override_settings(SHOW_INDEPENDENCE_BANNER=True)
    def test_enabled_uses_french_translations(self):
        response = self.client.get(
            reverse("dashboard"),
            HTTP_ACCEPT_LANGUAGE="fr",
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, INDEPENDENCE_MESSAGE_FR, count=2)
        self.assertContains(
            response,
            "Système d’approbation et de workflow Microcom",
        )

    @override_settings(SHOW_INDEPENDENCE_BANNER=True)
    def test_login_page_remains_clean(self):
        self.client.logout()
        response = self.client.get(
            reverse("login"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, 'class="independence-banner"')
        self.assertNotContains(response, 'class="independence-ribbon"')

    def test_print_templates_do_not_use_independence_elements(self):
        print_templates = [
            "templates/requests_app/approved_document.html",
            "templates/requests_app/permission_document.html",
            "templates/requests_app/bulk_print_material_documents.html",
        ]

        for template_path in print_templates:
            with self.subTest(template=template_path):
                with open(settings.BASE_DIR / template_path, encoding="utf-8") as template_file:
                    template_source = template_file.read()

                self.assertNotIn("base.html", template_source)
                self.assertNotIn("independence-banner", template_source)
                self.assertNotIn("independence-ribbon", template_source)
