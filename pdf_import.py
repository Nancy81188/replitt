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
DATE_PATTERNS = ((r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b", "dmy"), (r"\b(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})\b", "ymd"))
ARABIC_SUBTOTAL = ("المجموع الفرعي", "الاجمالي الفرعي", "المجموع قبل الضريبة",
                   "الاجمالي قبل الضريبة", "المبلغ قبل الضريبة",
                   "الاجمالي الخاضع للضريبة", "المبلغ الخاضع للضريبة")
ARABIC_VAT = ("ضريبة القيمة المضافة", "الضريبة على القيمة المضافة",
              "قيمة الضريبة", "مبلغ الضريبة", "ض.ق.م")
ARABIC_TOTAL = ("اجمالي الفاتورة", "المجموع الكلي", "المبلغ الاجمالي",
                "المبلغ المستحق", "الصافي للدفع", "الاجمالي", "المجموع")


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
                texts.append(pytesseract.image_to_string(image, lang=language, config=config))
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


def _vat_amount_after(text):
    """Read a VAT amount without mistaking a percentage on the line for money."""
    found = None
    for raw in text.splitlines():
        line = _normalize_amount_line(raw)
        if re.search(r"\b(?:vat|tva|tax)\s*(?:no\.?|number|registration|id)\b", line, re.I):
            continue
        if re.search(r"رقم\s*(?:التسجيل\s*)?الضريبة", line):
            continue
        for keyword in ("vat amount", "vat 11%", "vat", "tva", "tax", *ARABIC_VAT):
            end = _keyword_end(line, keyword)
            if end is None:
                continue
            suffix = line[end:]
            values = [
                _number(match.group())
                for match in re.finditer(AMOUNT, suffix)
                if not suffix[match.end():].lstrip().startswith(("%", "٪"))
            ]
            if values:
                found = values[-1]
            elif not keyword.isascii():
                prefix = line[:end - len(keyword)].strip()
                if re.fullmatch(rf"{AMOUNT}\s*[:\-]?", prefix):
                    found = _number(re.search(AMOUNT, prefix).group())
    return found


def _invoice_total_after(text):
    """Ignore lines that name the before-VAT total rather than the invoice total."""
    lines = [
        line for line in text.splitlines()
        if not re.search(r"\bsub[\s-]*total\b|\btotal\s+(?:ht|before|excl|without)\b", line, re.I)
        and not any(label in _normalize_amount_line(line) for label in ARABIC_SUBTOTAL)
        and not any(label in _normalize_amount_line(line) for label in ARABIC_VAT)
    ]
    return _amount_after("\n".join(lines), ("grand total", "total amount", "amount due", "net to pay", "total ttc", "total", *ARABIC_TOTAL))


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
        line = " ".join(raw.split())
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
    try: text = pdf_text(path)
    except Exception as exc: return {"file": path.name, "path": str(path), "text": "", "notes": f"The PDF could not be read ({exc}). Enter the details manually."}
    ocr_note = ""
    if len(text.strip()) < 20:
        try:
            text = _ocr_pdf(path)
            ocr_note = ("Local English/Arabic OCR suggestion - please check" if text.strip()
                        else "Local OCR found no readable text")
        except Exception as exc:
            ocr_note = f"Local OCR unavailable ({exc})"
    result = _parse_invoice_text(path, text)
    if ocr_note:
        result["ocr_used"] = bool(text.strip())
        result["notes"] = (ocr_note + "; " + result["notes"]) if result["notes"] else ocr_note
        if result["ocr_used"]:
            _warn_on_invoice_total_mismatch(result)
    return result


def _warn_on_invoice_total_mismatch(result):
    subtotal, vat, total = (result.get(key) for key in ("subtotal", "vat", "total"))
    if any(value is None for value in (subtotal, vat, total)):
        return
    if abs(subtotal + vat - total) > max(0.05, abs(total) * 0.005):
        result["vat"] = None
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
    match = re.search(r"(?:invoice|inv|facture|فاتورة|bill)\s*(?:no\.?|number|num|#|n°|رقم)?\s*[:#.]?\s*([A-Z0-9][A-Z0-9\-/]{1,24})", text, re.I)
    if match and any(ch.isdigit() for ch in match.group(1)): result["invoice_number"] = match.group(1).strip("-/")
    for pattern, order in DATE_PATTERNS:
        for groups in re.findall(pattern, text):
            try:
                day, month, year = (groups if order == "dmy" else (groups[2], groups[1], groups[0]))
                result["invoice_date"] = datetime(int(year), int(month), int(day)).strftime("%d-%m-%Y"); break
            except ValueError: continue
        if result["invoice_date"]: break
    upper = text.upper()
    for code, marks in (("LBP", ("LBP", "L.L", "ل.ل", "LL ")), ("EUR", ("EUR", "€")), ("AED", ("AED", "DHS")), ("USD", ("USD", "US$", "$"))):
        if any(mark in upper for mark in marks): result["currency"] = code; break
    result["total"] = _invoice_total_after(text)
    result["vat"] = _vat_amount_after(text)
    result["subtotal"] = _amount_after(text, ("subtotal", "sub-total", "sub total", "before vat", "total ht", "net amount", "excl", *ARABIC_SUBTOTAL))
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) >= 3 and not re.search(r"invoice|facture|date|tel|phone|page|www|@", clean, re.I) and sum(ch.isalpha() for ch in clean) >= 3:
            result["party_name"] = clean[:60]; break
    result["items"] = _line_items(text)
    missing = [label for key, label in (("invoice_number", "number"), ("invoice_date", "date"), ("total", "total")) if not result.get(key)]
    result["notes"] = "Read from PDF - please check" + (f"; not found: {', '.join(missing)}" if missing else "")
    if result["vat"] is None and any(re.search(r"\b(?:vat|tva|tax)\b|ض\.ق\.م|ضريبة", line, re.I)
                                       for line in text.splitlines()):
        result["notes"] += "; VAT amount not found; enter or confirm it manually"
    if result["items"]:
        result["notes"] += f"; {len(result['items'])} item row(s) pre-filled for review"
    return result


def read_invoice_pdf_pages(path):
    """Preview each distinct invoice in a PDF and retain its page range.

    A repeated invoice number on later pages is treated as a continuation. Pages
    without extractable text stay visible for manual entry, rather than vanishing.
    """
    from pypdf import PdfReader
    path = Path(path)
    reader = PdfReader(str(path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    blank_pages = [index for index, text in enumerate(page_texts) if len(text.strip()) < 20]
    ocr_error = ""
    if blank_pages:
        try:
            for index, text in zip(blank_pages, _ocr_pdf_pages(path, blank_pages)):
                if text.strip():
                    page_texts[index] = text
        except Exception as exc:
            ocr_error = f"; local OCR unavailable ({exc})"
    groups = []
    ocr_pages = set()
    for number, text in enumerate(page_texts, 1):
        if number - 1 in blank_pages and text.strip():
            ocr_pages.add(number)
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
        if parsed["ocr_used"]:
            parsed["notes"] = "Local OCR suggestion - please check; " + parsed["notes"]
            _warn_on_invoice_total_mismatch(parsed)
        if not parsed.get("invoice_number"):
            parsed["notes"] += "; confirm invoice boundaries and number" + ocr_error
        results.append(parsed)
    return results
