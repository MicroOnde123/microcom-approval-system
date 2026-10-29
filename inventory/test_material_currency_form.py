"""Database-free regression checks for the material admin currency selection."""
from unittest import TestCase
from unittest.mock import patch

from django.utils.translation import override

from core.document_config import Currency
from .admin import MaterialAdminForm
from .models import Material


class PriceForm(MaterialAdminForm):
    class Meta(MaterialAdminForm.Meta):
        fields = ('unit_price', 'currency')


class MaterialCurrencyFormTests(TestCase):
    def test_new_forms_default_to_usd_in_both_languages(self):
        for language in ('en', 'fr'):
            with self.subTest(language=language), override(language):
                form = MaterialAdminForm()
                self.assertEqual(form['currency'].value(), Currency.USD)
                self.assertEqual({value for value, label in form.fields['currency'].choices if value}, set(Currency.values))
                self.assertIsNone(form.instance.currency)

    def test_existing_saved_currencies_and_legacy_blank_are_preserved(self):
        for currency in [*Currency.values, None]:
            material = Material(pk=7, currency=currency)
            material._state.adding = False
            self.assertEqual(MaterialAdminForm(instance=material)['currency'].value(), currency)

    def test_explicit_initial_selection_is_preserved(self):
        self.assertEqual(MaterialAdminForm(initial={'currency': 'EUR'})['currency'].value(), 'EUR')

    def test_invalid_price_keeps_submitted_currency_in_both_languages(self):
        for language in ('en', 'fr'):
            for currency in Currency.values:
                with self.subTest(language=language, currency=currency), override(language):
                    form = PriceForm(data={'unit_price': '-1', 'currency': currency})
                    with patch.object(Material, 'validate_unique'), patch.object(Material, 'validate_constraints'):
                        self.assertFalse(form.is_valid())
                    self.assertIn('unit_price', form.errors)
                    self.assertEqual(form['currency'].value(), currency)

    def test_bound_blank_and_invalid_choices_are_not_replaced(self):
        for currency in ('', 'ZZZ'):
            form = PriceForm(data={'unit_price': '', 'currency': currency})
            self.assertEqual(form['currency'].value(), currency)

    def test_valid_new_pricing_preserves_explicit_selection_without_saving(self):
        for currency in Currency.values:
            form = PriceForm(data={'unit_price': '0', 'currency': currency})
            with patch.object(Material, 'validate_unique'), patch.object(Material, 'validate_constraints'):
                self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.instance.currency, currency)
            self.assertIsNone(form.instance.pk)
