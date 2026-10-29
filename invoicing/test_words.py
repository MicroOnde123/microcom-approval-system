from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .words import amount_in_french, integer_words


class FrenchAmountTests(SimpleTestCase):
    def test_traditional_cardinals_and_agreements(self):
        expected = {0:"zéro",1:"un",17:"dix-sept",21:"vingt et un",61:"soixante et un",
            70:"soixante-dix",71:"soixante et onze",72:"soixante-douze",80:"quatre-vingts",
            81:"quatre-vingt-un",91:"quatre-vingt-onze",99:"quatre-vingt-dix-neuf",
            100:"cent",200:"deux cents",201:"deux cent un",280:"deux cent quatre-vingts",
            1000:"mille",1001:"mille un",21000:"vingt et un mille",80000:"quatre-vingt mille",
            200000:"deux cent mille",280000:"deux cent quatre-vingt mille",
            200000000:"deux cents millions",80000000:"quatre-vingts millions",
            1000000000:"un milliard",10**12:"un billion",10**15:"un billiard"}
        for value,words in expected.items():
            with self.subTest(value=value):
                self.assertEqual(integer_words(value),words)

    def test_supported_currencies_and_subdivisions(self):
        for currency,words in {
            "USD":("zéro dollar américain","un dollar américain et un cent américain","deux dollars américains et quatre-vingt-dix-neuf cents américains"),
            "CDF":("zéro franc congolais","un franc congolais et un centime","deux francs congolais et quatre-vingt-dix-neuf centimes"),
            "EUR":("zéro euro","un euro et un centime","deux euros et quatre-vingt-dix-neuf centimes"),
        }.items():
            for amount,expected in zip(("0","1.01","2.99"),words):
                with self.subTest(currency=currency,amount=amount):
                    self.assertEqual(amount_in_french(Decimal(amount),currency),expected)

    def test_millions_and_maximum_financial_range(self):
        self.assertEqual(amount_in_french(Decimal("2000000"),"USD"),"deux millions de dollars américains")
        self.assertEqual(amount_in_french(Decimal("1000000.01"),"EUR"),"un million d’euros et un centime")
        self.assertEqual(amount_in_french(Decimal("1000001"),"CDF"),"un million un francs congolais")
        expected = " ".join(["neuf cent quatre-vingt-dix-neuf billiards", "neuf cent quatre-vingt-dix-neuf billions",
            "neuf cent quatre-vingt-dix-neuf milliards","neuf cent quatre-vingt-dix-neuf millions",
            "neuf cent quatre-vingt-dix-neuf mille","neuf cent quatre-vingt-dix-neuf euros et quatre-vingt-dix-neuf centimes"])
        self.assertEqual(amount_in_french(Decimal("999999999999999999.99"),"EUR"),expected)

    def test_invalid_or_inexact_amounts_fail(self):
        for amount in ("-1","0.001","NaN","Infinity","1000000000000000000",0.1,True):
            with self.subTest(amount=amount),self.assertRaises(ValidationError):
                amount_in_french(amount,"USD")
        with self.assertRaises(ValidationError):
            amount_in_french(Decimal("1"),"ZZZ")
