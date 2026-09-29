"""Amount in words (tafqeet) for invoices: Arabic and English, with the currency and its fraction."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CURRENCIES = {
    "USD": {"en": ("US Dollar", "US Dollars", "Cent", "Cents"), "ar": ("دولار أميركي", "دولاران أميركيان", "دولارات أميركية", "دولاراً أميركياً", "سنت", "سنتاً")},
    "LBP": {"en": ("Lebanese Pound", "Lebanese Pounds", "", ""), "ar": ("ليرة لبنانية", "ليرتان لبنانيتان", "ليرات لبنانية", "ليرة لبنانية", "", "")},
    "EUR": {"en": ("Euro", "Euros", "Cent", "Cents"), "ar": ("يورو", "يوروان", "يورو", "يورو", "سنت", "سنتاً")},
    "AED": {"en": ("UAE Dirham", "UAE Dirhams", "Fils", "Fils"), "ar": ("درهم إماراتي", "درهمان إماراتيان", "دراهم إماراتية", "درهماً إماراتياً", "فلس", "فلساً")},
}

_EN_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_EN_TENS = "  twenty thirty forty fifty sixty seventy eighty ninety".split(" ")


def _en_below_thousand(n):
    words = []
    if n >= 100: words += [_EN_ONES[n // 100], "hundred"]; n %= 100
    if n >= 20: words.append(_EN_TENS[n // 10] + ("-" + _EN_ONES[n % 10] if n % 10 else ""))
    elif n or not words: words.append(_EN_ONES[n])
    return " ".join(words)


def english(n):
    n = int(n)
    if n == 0: return "zero"
    parts = []
    for value, name in ((10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand"), (1, "")):
        if n >= value:
            chunk, n = divmod(n, value)
            parts.append(_en_below_thousand(chunk) + (f" {name}" if name else ""))
    return " ".join(parts)


_AR_ONES = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر",
            "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
_AR_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_AR_HUNDREDS = ["", "مئة", "مئتان", "ثلاثمئة", "أربعمئة", "خمسمئة", "ستمئة", "سبعمئة", "ثمانمئة", "تسعمئة"]
_AR_SCALES = [(10 ** 9, ("مليار", "ملياران", "مليارات")), (10 ** 6, ("مليون", "مليونان", "ملايين")), (1000, ("ألف", "ألفان", "آلاف"))]


def _ar_below_thousand(n):
    words = []
    if n >= 100: words.append(_AR_HUNDREDS[n // 100]); n %= 100
    if n >= 20:
        tens = _AR_TENS[n // 10]; words.append(f"{_AR_ONES[n % 10]} و{tens}" if n % 10 else tens)
    elif n: words.append(_AR_ONES[n])
    return " و".join(words)


def arabic(n):
    n = int(n)
    if n == 0: return "صفر"
    parts = []
    for value, (one, two, plural) in _AR_SCALES:
        if n >= value:
            chunk, n = divmod(n, value)
            if chunk == 1: parts.append(one)
            elif chunk == 2: parts.append(two)
            elif 3 <= chunk <= 10: parts.append(f"{_ar_below_thousand(chunk)} {plural}")
            else: parts.append(f"{_ar_below_thousand(chunk)} {one}")
    if n: parts.append(_ar_below_thousand(n))
    return " و".join(parts)


def _ar_counted(n, forms):
    one, two, plural, accusative = forms
    if n == 1: return one
    if n == 2: return two
    if 3 <= n % 100 <= 10: return f"{arabic(n)} {plural}"
    return f"{arabic(n)} {accusative}"


def amount_in_words(amount, currency="USD"):
    """{'en': 'One thousand three hundred ... US Dollars and 20 Cents only', 'ar': 'فقط ... لا غير'}"""
    value = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole = int(value); cents = int((value - whole) * 100)
    names = CURRENCIES.get(str(currency).upper(), CURRENCIES["USD"])
    en_one, en_many, en_cent, en_cents = names["en"]; ar = names["ar"]
    english_text = f"{english(whole).capitalize()} {en_one if whole == 1 else en_many}"
    if cents and en_cent: english_text += f" and {english(cents)} {en_cent if cents == 1 else en_cents}"
    arabic_text = _ar_counted(whole, ar[:4]) if whole else f"صفر {ar[2]}"
    if cents and ar[4]: arabic_text += f" و{_ar_counted(cents, (ar[4], ar[4] + 'ان', ar[4] + 'ات', ar[5]))}"
    return {"en": english_text + " only", "ar": f"فقط {arabic_text} لا غير"}
