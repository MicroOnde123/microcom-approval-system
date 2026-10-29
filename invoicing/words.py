"""Traditional French cardinal wording, long scale, exact two-decimal money."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

SMALL = ("zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
         "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize")
TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}
CURRENCIES = {
    "USD": ("dollar américain", "dollars américains", "cent américain", "cents américains"),
    "CDF": ("franc congolais", "francs congolais", "centime", "centimes"),
    "EUR": ("euro", "euros", "centime", "centimes"),
}
MAX_AMOUNT = Decimal("999999999999999999.99")


def _under_hundred(number, before_mille=False):
    if number < 17:
        return SMALL[number]
    if number < 20:
        return "dix-" + SMALL[number-10]
    if number < 70:
        ten, unit = divmod(number, 10)
        word = TENS[ten*10]
        return word if not unit else word + (" et " if unit==1 else "-") + SMALL[unit]
    if number < 80:
        return "soixante" + (" et " if number==71 else "-") + _under_hundred(number-60)
    if number==80:
        return "quatre-vingt" + ("" if before_mille else "s")
    return "quatre-vingt-" + _under_hundred(number-80)


def _group(number, before_mille=False):
    hundreds, rest = divmod(number,100)
    if not hundreds:
        return _under_hundred(rest,before_mille)
    prefix = "cent" if hundreds==1 else SMALL[hundreds]+" cent"
    if not rest:
        return prefix + ("s" if hundreds>1 and not before_mille else "")
    return prefix+" "+_under_hundred(rest,before_mille)


def integer_words(number):
    if not isinstance(number,int) or isinstance(number,bool) or not 0<=number<10**18:
        raise ValidationError(_("The amount exceeds the supported financial range."))
    if number==0:
        return SMALL[0]
    parts = []
    for scale,name in ((10**15,"billiard"),(10**12,"billion"),(10**9,"milliard"),(10**6,"million")):
        count,number = divmod(number,scale)
        if count:
            parts.append(_group(count)+" "+name+("s" if count>1 else ""))
    count,number = divmod(number,1000)
    if count:
        parts.append("mille" if count==1 else _group(count,True)+" mille")
    if number:
        parts.append(_group(number))
    return " ".join(parts)


def amount_in_french(amount, currency):
    if currency not in CURRENCIES or isinstance(amount,(float,bool)):
        raise ValidationError(_("Use an exact supported currency amount."))
    try:
        amount = Decimal(amount)
        if not amount.is_finite() or not 0<=amount<=MAX_AMOUNT or amount!=amount.quantize(Decimal("0.01")):
            raise InvalidOperation
    except (InvalidOperation,ValueError,TypeError):
        raise ValidationError(_("Use a nonnegative amount with at most two decimal places."))
    whole = int(amount)
    fraction = int((amount-whole)*100)
    singular,plural,sub_singular,sub_plural = CURRENCIES[currency]
    unit = singular if whole<2 else plural
    connector = (" d’" if currency=="EUR" else " de ") if whole and whole%10**6==0 else " "
    result = integer_words(whole)+connector+unit
    if fraction:
        result += " et "+integer_words(fraction)+" "+(sub_singular if fraction==1 else sub_plural)
    return result
