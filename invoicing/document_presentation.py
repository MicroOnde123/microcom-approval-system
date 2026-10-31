"""Language-aware presentation of frozen monetary amounts; never persistence."""
from decimal import Decimal
from .words import amount_in_french

_SMALL = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()


def _english(number):
    if number < 20:
        return _SMALL[number]
    if number < 100:
        ten, unit = divmod(number, 10)
        return _TENS[ten] + ("-" + _SMALL[unit] if unit else "")
    if number < 1000:
        hundred, rest = divmod(number, 100)
        return _SMALL[hundred] + " hundred" + (" and " + _english(rest) if rest else "")
    for scale, label in ((10**15, "quadrillion"), (10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        if number >= scale:
            count, rest = divmod(number, scale)
            return _english(count) + " " + label + (" " + _english(rest) if rest else "")


def amount_words(amount, currency, language, frozen_french):
    # Validate the exact stored amount, without rounding/repricing it.
    amount_in_french(amount, currency)
    if language == "fr":
        return frozen_french
    value = Decimal(amount)
    whole = int(value); fraction = int((value - whole) * 100)
    singular, plural = {"USD": ("US dollar", "US dollars"), "EUR": ("euro", "euros"),
                        "CDF": ("Congolese franc", "Congolese francs")}[currency]
    subunit = (" centime" if fraction == 1 else " centimes") if currency == "CDF" else (
        " cent" if fraction == 1 else " cents")
    return _english(whole) + " " + (singular if whole == 1 else plural) + (
        " and " + _english(fraction) + subunit if fraction else "")
