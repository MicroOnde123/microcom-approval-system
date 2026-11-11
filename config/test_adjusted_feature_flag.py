"""Test the real isolated settings assignment without loading application settings."""
import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from decouple import Config, RepositoryEmpty

class AdjustedFeatureFlagTests(unittest.TestCase):
    def value(self, supplied=None, environment=None):
        tree = ast.parse(Path(__file__).with_name('settings.py').read_text(encoding='utf8'))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'ADJUSTED_INVOICE_STATEMENTS_ENABLED' for t in node.targets))
        with patch.dict(os.environ, environment or {}, clear=True):
            if supplied is not None:
                os.environ['ADJUSTED_INVOICE_STATEMENTS_ENABLED'] = supplied
            scope = {'config': Config(RepositoryEmpty())}
            exec(compile(ast.Module(body=[assignment], type_ignores=[]), 'flag_assignment', 'exec'), scope)
            return scope['ADJUSTED_INVOICE_STATEMENTS_ENABLED']

    def test_absent_is_false(self):
        self.assertIs(self.value(), False)

    def test_explicit_false(self):
        self.assertIs(self.value('False'), False)
        self.assertIs(self.value('0'), False)

    def test_explicit_true(self):
        self.assertIs(self.value('True'), True)
        self.assertIs(self.value('1'), True)

    def test_invalid_value_rejected(self):
        for value in ('unexpected', 'enabled', 'True ', '2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.value(value)

    def test_unrelated_environment_does_not_enable(self):
        self.assertIs(self.value(environment={
            'DEBUG': 'True', 'MATERIAL_RETURN_NOTE_UI_ENABLED': 'True',
            'ADJUSTED_INVOICE_STATEMENTS': 'True', 'ADJUSTED_INVOICE_STATEMENTS_ENABLED_OTHER': 'True',
        }), False)

    def test_blank_is_disabled(self):
        self.assertIs(self.value(''), False)

    def test_actual_access_check_requires_boolean_true(self):
        source = Path(__file__).parents[1] / 'invoicing' / 'adjusted_access.py'
        function = next(node for node in ast.parse(source.read_text(encoding='utf8')).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'enabled')
        for value in (True, False, None, 'True', 'False', 1, 0):
            scope = {'settings': SimpleNamespace(ADJUSTED_INVOICE_STATEMENTS_ENABLED=value)}
            exec(compile(ast.Module(body=[function], type_ignores=[]), 'actual_access_check', 'exec'), scope)
            self.assertIs(scope['enabled'](), value is True)
