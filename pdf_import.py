"""Read invoice details from PDFs and expose reviewable line items.

Text-layer extraction is preferred. Scanned pages use local Tesseract OCR when
the optional OCR runtime is installed; invoice text is never sent elsewhere.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

AMOUNT = r"([0-9]{1,3}(?:[,\s][0-9]{3})+(?:\.[0-9]{1,3})?|[0-9]+(?:\.[0-9]{1,3})?)"
DATE_PATTERNS = (
    (r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})\b", "dmy"),
    (r"\b(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})\b", "ymd"),
)
ARABIC_SUBTOTAL = ("المجموع الفرعي", "الاجمالي الفرعي", "المجموع قبل الضريبة",
                   "الاجمالي قبل الضريبة", "المبلغ قبل الضريبة",
                   "الاجمالي الخاضع للضريبة", "المبلغ الخاضع للضريبة")
ARABIC_VAT = ("ضريبة القيمة المضافة", "الضريبة على القيمة المضافة",
              "قيمة الضريبة", "مبلغ الضريبة", "ض.ق.م")
ARABIC_TOTAL = ("اجمالي الفاتورة", "المجموع الكلي", "المبلغ الاجمالي",
                "المبلغ المستحق", "الصافي للدفع", "الاجمالي", "المجموع")
ENGLISH_MONTHS = {
    "jan": 1, "january": 1, "janv": 1, "janvier": 1,
    "feb": 2, "february": 2, "fev": 2, "fevr": 2, "févr": 2, "février": 2,
    "mar": 3, "march": 3, "mars": 3,
    "apr": 4, "april": 4, "avr": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6,
    "jul": 7, "july": 7, "juil": 7, "juillet": 7,
    "aug": 8, "august": 8, "aout": 8, "août": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12, "déc": 12, "décembre": 12,
}
CURRENCY_CODE = re.compile(r"\b(USD|EUR|AED|LBP)\b", re.I)


def _normalize_amount_line(line):
    """Normalize OCR Arabic digits, separators, hamza and vowel marks for label matching."""
    line = line.translate(str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬أإآٱ",
        "01234567890123456789.,اااا",
    ))
    return re.sub(r"[\u0640\u064b-\u065f\u0670]", "", line)


def pdf_text(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _ocr_pdf_pages(path, page_numbers=None):
    """OCR selected zero-based PDF pages locally, with the bundled engine if frozen."""
    import pypdfium2 as pdfium
    import pytesseract

    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    ocr_root = bundle_root / "ocr"
    engine = ocr_root / "engine"
    tessdata = ocr_root / "tessdata"
    if getattr(sys, "frozen", False):
        executable = engine / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
        if not executable.is_file():
            raise RuntimeError("The bundled Tesseract OCR engine is missing")
        pytesseract.pytesseract.tesseract_cmd = str(executable)

    config = "--psm 6"
    if tessdata.is_dir():
        config += f' --tessdata-dir "{tessdata}"'
    english_config = "--psm 4"
    if tessdata.is_dir():
        english_config += f' --tessdata-dir "{tessdata}"'
    try:
        available = set(pytesseract.get_languages(config=config))
    except Exception as exc:
        raise RuntimeError(f"Tesseract language data is unavailable ({exc})") from exc
    languages = [lang for lang in ("eng", "ara") if lang in available]
    if not languages:
        raise RuntimeError("Install English or Arabic Tesseract language data to read scanned invoices")
    language = "+".join(languages)

    document = pdfium.PdfDocument(str(path))
    selected = range(len(document)) if page_numbers is None else page_numbers
    texts = []
    try:
        for page_number in selected:
            page = document[int(page_number)]
            bitmap = None
            image = None
            try:
                bitmap = page.render(scale=2.0)
                image = bitmap.to_pil()
                text = pytesseract.image_to_string(image, lang=language, config=config)
                # PSM 6 with both languages can mistake a clear English invoice
                # heading for another word. If key invoice fields are missing,
                # retry locally with English layout analysis and keep the better
                # extraction; Arabic OCR remains the preferred result when it
                # yields more usable fields.
                parsed = _parse_invoice_text(path, text)
                subtotal, vat, total = (
                    parsed.get(key) for key in ("subtotal", "vat", "total")
                )
                amounts_conflict = (
                    all(value is not None for value in (subtotal, vat, total))
                    and abs(subtotal + vat - total) > max(0.05, abs(total) * 0.005)
                )
                core_fields_missing = any(
                    parsed.get(key) in (None, "")
                    for key in ("invoice_number", "invoice_date", "total")
                )
                if "eng" in languages and (core_fields_missing or amounts_conflict):
                    alternate = pytesseract.image_to_string(
                        image, lang="eng", config=english_config
                    )
                    if _ocr_invoice_score(path, alternate) > _ocr_invoice_score(path, text):
                        text = alternate
                texts.append(text)
            finally:
                if image is not None:
                    image.close()
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        document.close()
    return texts


def _ocr_pdf(path, page_numbers=None):
    return "\n".join(_ocr_pdf_pages(path, page_numbers))


def _ocr_invoice_score(path, text):
    parsed = _parse_invoice_text(path, text)
    weights = {
        "invoice_number": 2,
        "invoice_date": 2,
        "currency": 1,
        "subtotal": 1,
        "vat": 1,
        "total": 2,
    }
    score = sum(weight for key, weight in weights.items()
                if parsed.get(key) not in (None, ""))
    subtotal, vat, total = (parsed.get(key) for key in ("subtotal", "vat", "total"))
    if all(value is not None for value in (subtotal, vat, total)):
        tolerance = max(0.05, abs(total) * 0.005)
        score += 4 if abs(subtotal + vat - total) <= tolerance else -1
    return score


def _invoice_text_needs_ocr(path, text):
    """Retry weak text layers with OCR instead of treating any extracted text as usable."""
    if len((text or "").strip()) < 20:
        return True
    parsed = _parse_invoice_text(path, text)
    return parsed.get("total") is None or (
        not parsed.get("invoice_number") and not parsed.get("invoice_date")
    )


def _number(text):
    try: return float(str(text).replace(",", "").replace(" ", ""))
    except ValueError: return None


def _keyword_end(line, keyword):
    """Find a label without matching 'total' in 'subtotal' or 'tax' in 'taxable'."""
    if keyword.isascii():
        for match in re.finditer(rf"(?<![A-Za-z]){re.escape(keyword)}(?![A-Za-z])", line, re.I):
            if keyword == "total" and re.search(r"sub[\s-]*$", line[:match.start()], re.I):
                continue
            return match.end()
        return None
    position = line.find(keyword)
    return position + len(keyword) if position >= 0 else None


def _amount_after(text, keywords):
    """Last same-line labelled amount (also accepts Arabic RTL number-first OCR)."""
    found = None
    for raw in text.splitlines():
        line = _normalize_amount_line(raw)
        for keyword in keywords:
            end = _keyword_end(line, keyword)
            if end is None: continue
            numbers = re.findall(AMOUNT, line[end:])
            values = [v for v in (_number(n) for n in numbers) if v is not None]
            if values:
                found = values[-1]
            elif not keyword.isascii():
                # Tesseract may emit RTL rows as "١١١٫٠٠ : المجموع الكلي".
                prefix = line[:end - len(keyword)].strip()
                if re.fullmatch(rf"{AMOUNT}\s*[:\-]?", prefix):
                    found = _number(re.search(AMOUNT, prefix).group())
    return found


def _vat_amount_after(text, invoice_currency=""):
    """Read the VAT in the invoice currency, not its translated LBP equivalent."""
    if invoice_currency:
        inline = re.compile(
            rf"{AMOUNT}\s*{re.escape(invoice_currency)}\s*VAT\b", re.I
        )
        for line in text.splitlines():
            match = inline.search(line)
            if match:
                value = _number(match.group(1))
                if value is not None:
                    return value

    found = None
    best_score = 0
    for raw in text.splitlines():
        line = _normalize_amount_line(raw)
        line = re.sub(r"(?i)\bv\s*\.?\s*a\s*\.?\s*t\s*\.?\b", "VAT", line)
        if re.search(
            r"\b(?:vat|tva|tax)\b.{0,35}\b(?:account|a/c|no\.?|number|registration|id)\b",
            line, re.I,
        ):
            continue
        if re.search(r"\b(?:vat|tva|tax)\s*#", line, re.I):
            continue
        if re.search(
            r"\bpaid\s+on\s+behalf\b|\bbefore\s+vat\b|\btotal\s+(?:ht|excl|without)\s+vat\b",
            line, re.I,
        ):
            continue
        if re.search(r"رقم\s*(?:التسجيل\s*)?الضريبة", line):
            continue
        for keyword in ("vat amount", "vat 11%", "vat", "tva", "tax", *ARABIC_VAT):
            end = _keyword_end(line, keyword)
            if end is None:
                continue
            suffix = line[end:]
            amount_matches = [
                match for match in re.finditer(AMOUNT, suffix)
                if not suffix[match.end():].lstrip().startswith(("%", "٪"))
            ]
            values = [_number(match.group(1)) for match in amount_matches]
            values = [(match, value) for match, value in zip(amount_matches, values)
                      if value is not None]
            if values:
                currencies = list(CURRENCY_CODE.finditer(suffix))
                matching_currency = [
                    match for match in currencies
                    if match.group(1).upper() == invoice_currency.upper()
                ] if invoice_currency else []
                if matching_currency:
                    currency_position = matching_currency[0].start()
                    amount_match, value = min(
                        values,
                        key=lambda pair: abs(
                            (pair[0].start() + pair[0].end()) / 2 - currency_position
                        ),
                    )
                    score = 3
                elif currencies:
                    first_currency_position = currencies[0].start()
                    before_currency = [
                        (match, value) for match, value in values
                        if match.end() <= first_currency_position
                    ]
                    if before_currency:
                        amount_match, value = before_currency[-1]
                        score = 2
                    elif invoice_currency:
                        # The only amount is explicitly labelled in another
                        # currency, so don't treat an exchange conversion as VAT.
                        continue
                    else:
                        amount_match, value = values[-1]
                        score = 1
                else:
                    amount_match, value = values[-1]
                    score = 1
                if score >= best_score:
                    found = value
                    best_score = score
            elif not keyword.isascii():
                prefix = line[:end - len(keyword)].strip()
                if re.fullmatch(rf"{AMOUNT}\s*[:\-]?", prefix):
                    found = _number(re.search(AMOUNT, prefix).group())
    return found


def _invoice_number(text):
    pattern = re.compile(
        r"(?:invoice|inv|facture|فاتورة|رقم\s*(?:ال)?فاتورة|n°\s*facture|bill)"
        r"\s*(?:no\.?|number|num|#|n°|رقم)?\s*[:#.]?\s*([A-Z\d][A-Z\d\-/]{1,24})",
        re.I,
    )
    for match in pattern.finditer(text):
        candidate = _normalize_amount_line(match.group(1)).strip("-/")
        if any(char.isdigit() for char in candidate):
            return candidate

    # Some invoice templates visually put the number before the "INVOICE NO"
    # label; pypdf preserves that text order instead of the reading order.
    for match in re.finditer(
        r"(?<![A-Za-z])(?:invoice|inv|facture)\s*(?:no\.?|number|#)", text, re.I
    ):
        line_start = text.rfind("\n", 0, match.start()) + 1
        prefix = text[line_start:match.start()]
        leading_number = re.match(
            r"\s*([A-Z\d][A-Z\d\-/]{1,24})\s+"
            r"(?=(?:\d{1,2}\s+[A-Za-zÀ-ÿ]{3,10}[., ]+\d{4}|"
            r"[A-Za-zÀ-ÿ]{3,10}\s+\d{1,2},?\s+\d{4})\b)",
            prefix, re.I,
        )
        if leading_number and any(char.isdigit() for char in leading_number.group(1)):
            return leading_number.group(1)

    reference = _document_reference_number(text)
    if reference:
        return reference
    return ""


def _document_reference_number(text):
    pattern = re.compile(
        r"(?<![A-Za-z])(?:ref(?:erence)?|document\s+(?:ref|reference))"
        r"\s*(?:nb\s*)?(?:no\.?|number|#|n°)?\s*[:#.]?\s*"
        r"([A-Z\d][A-Z\d\-/]{1,24})",
        re.I,
    )
    for match in pattern.finditer(text):
        candidate = _normalize_amount_line(match.group(1)).strip("-/")
        if any(char.isdigit() for char in candidate):
            return candidate
    return ""


def _invoice_date(text):
    for pattern, order in DATE_PATTERNS:
        for groups in re.findall(pattern, text):
            try:
                day, month, year = (
                    groups if order == "dmy" else (groups[2], groups[1], groups[0])
                )
                return datetime(_expand_year(year), int(month), int(day)).strftime("%d-%m-%Y")
            except ValueError:
                continue

    month_date = re.compile(
        r"\b(?:(\d{1,2})[./\-\s]+([A-Za-zÀ-ÿ]{3,10})[.,/\-\s]+(\d{2}|\d{4})"
        r"|([A-Za-zÀ-ÿ]{3,10})[.,]?\s+(\d{1,2}),?\s+(\d{2}|\d{4}))\b",
        re.I,
    )
    for match in month_date.finditer(text):
        if match.group(1):
            day, month_name, year = match.group(1, 2, 3)
        else:
            month_name, day, year = match.group(4, 5, 6)
        month = ENGLISH_MONTHS.get(month_name.casefold().rstrip("."))
        if month is None:
            continue
        try:
            return datetime(_expand_year(year), month, int(day)).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return ""


def _expand_year(year):
    year = int(year)
    if year < 100:
        return 2000 + year if year <= 49 else 1900 + year
    return year


def _currency_from_total_context(segment):
    """Prefer a currency symbol adjacent to the total over unrelated bank details."""
    if re.search(r"\bUSD\b|\bUS\s*\$", segment, re.I):
        return "USD"
    if "$" in segment:
        return "USD"
    if re.search(r"\bEUR\b|€", segment, re.I):
        return "EUR"
    if re.search(r"\bAED\b|\bDHS\b|د\s*\.?\s*إ", segment, re.I):
        return "AED"
    match = CURRENCY_CODE.search(segment)
    return match.group(1).upper() if match else ""


def _invoice_currency(text):
    codes = r"(USD|EUR|AED|LBP)"
    lines = text.splitlines()
    for line in lines:
        match = re.search(rf"\b(?:the\s+)?sum\s+of\s+{codes}\b", line, re.I)
        if match:
            return match.group(1).upper()
        match = re.search(rf"\btotal\s*\(\s*{codes}\s*\)", line, re.I)
        if match:
            return match.group(1).upper()

    for index, line in enumerate(lines):
        if not re.search(r"\b(?:grand\s+)?total\b|\bamount\s+due\b", line, re.I):
            continue
        if re.search(r"\bsub[\s-]*total\b|\btotal\s+(?:before|ht|excl|without)\b", line, re.I):
            continue
        segment = " ".join(lines[index:index + 4])
        currency = _currency_from_total_context(segment)
        if currency:
            return currency

    upper = text.upper()
    for code, marks in (
        ("LBP", ("LBP", "L.L", "ل.ل", "LL ")),
        ("EUR", ("EUR", "€")),
        ("AED", ("AED", "DHS")),
        ("USD", ("USD", "US$")),
    ):
        if any(mark in upper for mark in marks):
            return code
    return ""


def _invoice_total_after(text):
    """Ignore lines that name the before-VAT total rather than the invoice total."""
    lines = [
        line for line in text.splitlines()
        if not re.search(r"\bsub[\s-]*total\b|\btotal\s+(?:ht|before|excl|without)\b", line, re.I)
        and not any(label in _normalize_amount_line(line) for label in ARABIC_SUBTOTAL)
        and not any(label in _normalize_amount_line(line) for label in ARABIC_VAT)
    ]
    return _amount_after(
        "\n".join(lines),
        ("grand total", "total amount", "amount due", "net to pay", "total ttc",
         "sum of", "total", *ARABIC_TOTAL),
    )


def _subtotal_from_tax_breakdown(text):
    """Read an unqualified Total as pre-tax only when VAT and Grand Total follow."""
    lines = [_normalize_amount_line(line) for line in text.splitlines()]
    grand_total = next(
        (index for index, line in enumerate(lines)
         if re.search(r"\bgrand\s+total\b", line, re.I)),
        None,
    )
    if grand_total is None:
        return None

    for index, line in enumerate(lines[:grand_total]):
        if not re.search(r"\btotal\b", line, re.I):
            continue
        if re.search(r"\b(?:grand|sub[\s-]*)total\b|\btotal\s+(?:before|ht|excl|without)\b",
                     line, re.I):
            continue
        vat_index = next(
            (
                line_index
                for line_index in range(index + 1, grand_total)
                if (
                    re.search(r"\b(?:vat|tva|tax)\b", lines[line_index], re.I)
                    or any(label in lines[line_index] for label in ARABIC_VAT)
                )
                and not re.search(
                    r"\b(?:account|a/c|number|registration|id)\b",
                    lines[line_index],
                    re.I,
                )
            ),
            None,
        )
        if vat_index is None:
            continue

        value = _amount_after(line, ("total",))
        if value is not None:
            return value

        # Some PDF text layers split the label, currency symbol, and amount
        # onto nearby lines. Do not cross the VAT label while looking for it.
        for following in lines[index + 1:min(vat_index, index + 4)]:
            numbers = re.findall(AMOUNT, following)
            values = [value for value in (_number(number) for number in numbers)
                      if value is not None]
            if values:
                return values[-1]
    return None


def _line_items(text):
    """Best-effort extraction of common invoice item rows.

    Invoice layouts differ too much for this to be an automatic posting
    decision.  These rows are only pre-filled into the review screen.  A row
    must end in quantity, unit price and line total, which avoids treating
    supplier address/phone lines as products.
    """
    items = []
    ignored = re.compile(
        r"invoice|facture|subtotal|sub-total|total|vat|tva|tax|amount|date|phone|tel|"
        r"page|discount|shipping|freight|currency|due|رقم|فاتورة|ضريبة",
        re.I,
    )
    number = r"[0-9]{1,3}(?:[,\s][0-9]{3})*(?:\.[0-9]{1,3})?|[0-9]+(?:\.[0-9]{1,3})?"
    row_pattern = re.compile(
        rf"^\s*(?P<description>.+?)\s+(?P<quantity>{number})\s+"
        rf"(?P<unit_price>{number})\s+(?P<total>{number})\s*$"
    )
    for raw in text.splitlines():
        line = " ".join(_normalize_amount_line(raw).split())
        if len(line) < 5 or ignored.search(line):
            continue
        match = row_pattern.match(line)
        if not match:
            continue
        description = match.group("description").strip(" -:|")
        if len(description) < 2 or not any(ch.isalpha() for ch in description):
            continue
        quantity = _number(match.group("quantity"))
        unit_price = _number(match.group("unit_price"))
        total = _number(match.group("total"))
        if quantity is None or unit_price is None or total is None or quantity <= 0:
            continue
        if abs(quantity * unit_price - total) > max(0.05, abs(total) * 0.03):
            continue
        items.append({
            "description": description[:160],
            "quantity": quantity,
            "unit_price": unit_price,
            "total": total,
            "unit": "unit",
        })
    return items[:200]


def suggest_invoice_type(text):
    """Conservative PDF category suggestion, never a posting decision.

    An invoice alone does not establish whether an expense has been paid or
    whether goods are held for resale. Conflicting or weak clues need review.
    """
    clues = {
        "Assets": (
            r"\bfixed assets?\b", r"\bcapital (?:asset|expenditure)\b",
            r"\boffice (?:furniture|equipment)\b", r"أصول ثابتة", r"موجودات ثابتة",
            r"immobilisation(?:s)?",
        ),
        "Purchases": (
            r"\b(?:goods|stock) for resale\b", r"\braw materials?\b",
            r"\bmerchandise\b", r"بضاعة", r"مواد أولية", r"marchandises",
        ),
        "Expenses": (
            r"\b(?:office|monthly) rent\b", r"\belectricity\b", r"\binternet service\b",
            r"\bconsulting (?:fee|service)\b", r"\bmaintenance (?:fee|service)\b",
            r"إيجار", r"كهرباء", r"اشتراك انترنت", r"loyer", r"électricité",
        ),
    }
    found = [category for category, patterns in clues.items()
             if any(re.search(pattern, text or "", re.I) for pattern in patterns)]
    return found[0] if len(found) == 1 else ""


def read_invoice_pdf(path):
    """Best guess of invoice number, date, party, currency and amounts. Always review before saving."""
    path = Path(path)
    text_error = ""
    try:
        text = pdf_text(path)
    except Exception as exc:
        text = ""
        text_error = str(exc)
    result = _parse_invoice_text(path, text)
    if not _invoice_text_needs_ocr(path, text):
        if text_error:
            result["notes"] = f'{result["notes"]}; PDF text extraction failed ({text_error})'.strip("; ")
        return result

    try:
        ocr_text = _ocr_pdf(path)
    except Exception as exc:
        result["ocr_used"] = False
        ocr_note = f"Local OCR unavailable ({exc})"
        if text_error:
            ocr_note += f"; PDF text extraction failed ({text_error})"
        result["notes"] = f'{result.get("notes", "")}; {ocr_note}'.strip("; ")
        return result

    if not ocr_text.strip():
        result["ocr_used"] = False
        ocr_note = "Local OCR found no readable text"
        if text_error:
            ocr_note += f"; PDF text extraction failed ({text_error})"
        result["notes"] = f'{result.get("notes", "")}; {ocr_note}'.strip("; ")
        return result

    ocr_result = _parse_invoice_text(path, ocr_text)
    result = _merge_invoice_suggestions(result, ocr_result)
    combined_text = "\n".join(part for part in (text.strip(), ocr_text.strip()) if part)
    result["text"] = combined_text
    result["ocr_used"] = True
    prefix = "Local English/Arabic OCR suggestion - please check"
    if len(text.strip()) < 20:
        prefix = "Scanned PDF; " + prefix
    if text_error:
        prefix += f"; PDF text extraction failed ({text_error})"
    result["notes"] = _invoice_notes(result, combined_text, prefix=prefix)
    _warn_on_invoice_total_mismatch(result)
    return result


def _warn_on_invoice_total_mismatch(result):
    subtotal, vat, total = (result.get(key) for key in ("subtotal", "vat", "total"))
    if any(value is None for value in (subtotal, vat, total)):
        return
    if abs(subtotal + vat - total) > max(0.05, abs(total) * 0.005):
        result["vat"] = None
        result["acquisition_cost"] = None
        warning = "OCR VAT, subtotal and total do not reconcile; VAT suggestion cleared. Enter and verify the amounts before posting"
        if warning not in result.get("notes", ""):
            result["notes"] = (result.get("notes", "") + "; " + warning).strip("; ")


def _parse_invoice_text(path, text):
    path = Path(path)
    result = {"file": path.name, "path": str(path), "text": text, "invoice_number": "", "invoice_date": "", "party_name": "", "currency": "",
              "subtotal": None, "vat": None, "total": None, "items": [], "notes": ""}
    result["suggested_type"] = suggest_invoice_type(text)
    if len(text.strip()) < 20:
        result["notes"] = "This PDF is a scanned image (no text inside). The file will be attached; enter the amounts manually."; return result
    result["invoice_number"] = _invoice_number(text)
    result["invoice_date"] = _invoice_date(text)
    result["currency"] = _invoice_currency(text)
    result["total"] = _invoice_total_after(text)
    result["vat"] = _vat_amount_after(text, result["currency"])
    result["subtotal"] = _amount_after(text, ("subtotal", "sub-total", "sub total", "before vat", "total ht", "net amount", "excl", *ARABIC_SUBTOTAL))
    if result["subtotal"] is None:
        result["subtotal"] = _subtotal_from_tax_breakdown(text)
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) >= 3 and not re.search(r"invoice|facture|date|tel|phone|page|www|@", clean, re.I) and sum(ch.isalpha() for ch in clean) >= 3:
            result["party_name"] = clean[:60]; break
    result["items"] = _line_items(text)
    # For a fixed-asset register preview, use a description only when the PDF
    # yields one unambiguous item (or an explicitly labelled asset/description).
    if len(result["items"]) == 1:
        result["asset_name"] = result["items"][0]["description"]
    else:
        named = re.search(
            r"(?im)^\s*(?:asset|item|description|equipment|الموجودات|الأصل|الصنف)\s*[:\-]\s*(.{3,100}?)\s*$",
            text,
        )
        result["asset_name"] = named.group(1).strip() if named else ""
    # A labelled subtotal is the conservative acquisition-cost candidate.
    # A grand total is usable only when the PDF explicitly says VAT is zero.
    result["acquisition_cost"] = result["subtotal"]
    if result["acquisition_cost"] is None and result["vat"] == 0:
        result["acquisition_cost"] = result["total"]
    result["notes"] = _invoice_notes(result, text)
    return result


def _merge_invoice_suggestions(primary, fallback):
    """Fill gaps from OCR while keeping values read from the PDF text layer preferred."""
    result = dict(primary)
    for key in ("invoice_number", "invoice_date", "party_name", "currency", "subtotal", "vat",
                "total", "items", "suggested_type", "asset_name", "acquisition_cost"):
        value = result.get(key)
        if value is None or value == "" or value == []:
            replacement = fallback.get(key)
            if replacement is not None and replacement != "" and replacement != []:
                result[key] = replacement
    return result


def _invoice_notes(result, text, prefix=""):
    missing = [label for key, label in (("invoice_number", "number"), ("invoice_date", "date"),
                                        ("total", "total")) if not result.get(key)]
    notes = []
    if prefix:
        notes.append(prefix)
    notes.append("Read from PDF - please check" +
                 (f"; not found: {', '.join(missing)}" if missing else ""))
    reference = _document_reference_number(text)
    if reference and result.get("invoice_number") == reference:
        notes.append("Document reference suggested as invoice number; verify before posting")
    if result.get("vat") is None and any(
            re.search(r"\b(?:vat|tva|tax)\b|ض\.ق\.م|ضريبة", line, re.I)
            for line in text.splitlines()):
        notes.append("VAT amount not found; enter or confirm it manually")
    if result.get("items"):
        notes.append(f"{len(result['items'])} item row(s) pre-filled for review")
    return "; ".join(notes)


def asset_pdf_details(data):
    """Return conservative fixed-asset suggestions; absent/ambiguous values stay blank."""
    date_text = ""
    raw_date = data.get("invoice_date") or ""
    for pattern in ("%d-%m-%Y", "%Y-%m-%d", "%d%m%Y"):
        try:
            date_text = datetime.strptime(raw_date, pattern).strftime("%d-%m-%Y")
            break
        except ValueError:
            continue
    return {
        "name": (data.get("asset_name") or "").strip(),
        "acquired_on": date_text,
        "currency": (data.get("currency") or "").upper(),
        "cost": data.get("acquisition_cost"),
    }


def read_invoice_pdf_pages(path):
    """Preview each distinct invoice in a PDF and retain its page range.

    A repeated invoice number on later pages is treated as a continuation. Pages
    without extractable text stay visible for manual entry, rather than vanishing.
    """
    from pypdf import PdfReader
    path = Path(path)
    reader = PdfReader(str(path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    blank_pages = {index for index, text in enumerate(page_texts) if len(text.strip()) < 20}
    ocr_candidate_pages = [
        index for index, text in enumerate(page_texts)
        if _invoice_text_needs_ocr(path, text)
    ]
    ocr_error = ""
    ocr_pages = set()
    if ocr_candidate_pages:
        try:
            for index, text in zip(ocr_candidate_pages, _ocr_pdf_pages(path, ocr_candidate_pages)):
                if text.strip():
                    page_texts[index] = text
                    ocr_pages.add(index + 1)
        except Exception as exc:
            ocr_error = str(exc)
    groups = []
    for number, text in enumerate(page_texts, 1):
        parsed = _parse_invoice_text(path, text)
        invoice_number = parsed.get("invoice_number")
        if groups and invoice_number and invoice_number == groups[-1]["invoice_number"]:
            groups[-1]["text"] += "\n" + text
            groups[-1]["pages"].append(number)
        elif groups and not invoice_number and text.strip() and not parsed.get("total"):
            groups[-1]["text"] += "\n" + text
            groups[-1]["pages"].append(number)
        else:
            groups.append({"invoice_number":invoice_number,"text":text,"pages":[number]})
    results = []
    for group in groups:
        parsed = _parse_invoice_text(path, group["text"])
        pages = group["pages"]
        parsed["page_range"] = f"Page {pages[0]}" if len(pages)==1 else f"Pages {pages[0]}-{pages[-1]}"
        parsed["ocr_used"] = any(number in ocr_pages for number in pages)
        needs_ocr = any(number - 1 in ocr_candidate_pages for number in pages)
        if parsed["ocr_used"]:
            prefix = ("Scanned PDF; " if any(number - 1 in blank_pages for number in pages) else "")
            parsed["notes"] = _invoice_notes(
                parsed, group["text"], prefix=prefix + "Local OCR suggestion - please check",
            )
            _warn_on_invoice_total_mismatch(parsed)
        elif needs_ocr:
            note = (f"Local OCR unavailable ({ocr_error})" if ocr_error
                    else "Local OCR found no readable text")
            parsed["notes"] = f'{parsed["notes"]}; {note}'.strip("; ")
        if not parsed.get("invoice_number"):
            parsed["notes"] += "; confirm invoice boundaries and number"
        results.append(parsed)
    return results
