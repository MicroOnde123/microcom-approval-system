"""Render real counter markup and exercise its JavaScript without a database."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase
from django.utils.translation import override
from html.parser import HTMLParser


class CounterParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


class ReportCounterTranslationTests(SimpleTestCase):
    def test_rendered_english_and_french_dynamic_counts(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required to verify the dynamic counter.')
        root = Path(settings.BASE_DIR)
        source = (root / 'templates/requests_app/material_reports.html').read_text(encoding='utf-8')
        start = source.index('<span id="report-selection-count"')
        fragment = source[start:source.index('</span>', start) + len('</span>')]
        for language, expected in (
            ('en', ['0 requests selected', '1 request selected', '3 requests selected']),
            ('fr', ['0 demande sélectionnée', '1 demande sélectionnée', '3 demandes sélectionnées']),
        ):
            with self.subTest(language=language), override(language):
                rendered = Template('{% load i18n %}' + fragment).render(Context())
                self.assertIn('>' + expected[0] + '</span>', rendered)
                parser = CounterParser()
                parser.feed(rendered)
                labels = {key: parser.attrs[attr] for key, attr in (
                    ('labelZero', 'data-label-zero'), ('labelOne', 'data-label-one'), ('label', 'data-label'),
                )}
                env = dict(os.environ, REPORT_COUNTER_TRANSLATION=json.dumps({'labels': labels, 'expected': expected}))
                result = subprocess.run(
                    [node, '--test', '--test-isolation=none', 'requests_app/js_tests/material_report_selection.test.cjs'],
                    cwd=root, env=env, capture_output=True, text=True, encoding='utf-8',
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
