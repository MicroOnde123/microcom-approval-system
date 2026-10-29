"""Template configuration for mocked HTTP contract tests, not authorization tests."""
from copy import deepcopy
from django.conf import settings
from django.test import override_settings


def isolate_mock_context(test):
    templates = deepcopy(settings.TEMPLATES)
    for backend in templates:
        processors = backend.get("OPTIONS", {}).get("context_processors", [])
        backend.setdefault("OPTIONS", {})["context_processors"] = [
            path for path in processors if path not in {
                "requests_app.context_processors.pending_approval_count",
                "core.context_processors.drc_match_banner",
            }
        ]
    override = override_settings(TEMPLATES=templates)
    override.enable()
    test.addCleanup(override.disable)
