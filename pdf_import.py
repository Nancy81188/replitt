"""Read invoice details from a PDF (text-based PDFs; scanned images need manual entry)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

AMOUNT = r"([0-9]{1,3}(?:[,\s][0-9]{3})+(?:\.[0-9]{1,3})?|[0-9]+(?:\.[0-9]{1,3})?)"
DATE_PATTERNS = ((r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b", "dmy"), (r"\b(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})\b", "ymd"))


def pdf_text(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _number(text):
    try: return float(str(text).replace(",", "").replace(" ", ""))
    except ValueError: return None


def _amount_after(text, keywords):
    """Last amount that follows one of the keywords on the same line."""
    found = None
    for line in text.splitlines():
        low = line.casefold()
        for keyword in keywords:
            position = low.find(keyword)
            if position < 0: continue
            numbers = re.findall(AMOUNT, line[position + len(keyword):])
            values = [v for v in (_number(n) for n in numbers) if v is not None]
            if values: found = values[-1]
    return found


def read_invoice_pdf(path):
    """Best guess of invoice number, date, party, currency and amounts. Always review before saving."""
    path = Path(path)
    try: text = pdf_text(path)
    except Exception as exc: return {"file": path.name, "path": str(path), "text": "", "notes": f"The PDF could not be read ({exc}). Enter the details manually."}
    return _parse_invoice_text(path, text)


def _parse_invoice_text(path, text):
    path = Path(path)
    result = {"file": path.name, "path": str(path), "text": text, "invoice_number": "", "invoice_date": "", "party_name": "", "currency": "",
              "subtotal": None, "vat": None, "total": None, "notes": ""}
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
    result["total"] = _amount_after(text, ("grand total", "total amount", "amount due", "net to pay", "total ttc", "total"))
    result["vat"] = _amount_after(text, ("vat amount", "vat 11%", "vat", "tva", "tax", "ض.ق.م"))
    result["subtotal"] = _amount_after(text, ("subtotal", "sub-total", "sub total", "before vat", "total ht", "net amount", "excl"))
    if result["total"] and result["vat"] and not result["subtotal"]: result["subtotal"] = round(result["total"] - result["vat"], 2)
    if result["subtotal"] and result["vat"] is None: result["vat"] = round(result["subtotal"] * 0.11, 2)
    if result["subtotal"] and result["vat"] is not None and not result["total"]: result["total"] = round(result["subtotal"] + result["vat"], 2)
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) >= 3 and not re.search(r"invoice|facture|date|tel|phone|page|www|@", clean, re.I) and sum(ch.isalpha() for ch in clean) >= 3:
            result["party_name"] = clean[:60]; break
    missing = [label for key, label in (("invoice_number", "number"), ("invoice_date", "date"), ("total", "total")) if not result.get(key)]
    result["notes"] = "Read from PDF - please check" + (f"; not found: {', '.join(missing)}" if missing else "")
    return result


def read_invoice_pdf_pages(path):
    """Preview each distinct invoice in a PDF and retain its page range.

    A repeated invoice number on later pages is treated as a continuation. Pages
    without extractable text stay visible for manual entry, rather than vanishing.
    """
    from pypdf import PdfReader
    path = Path(path)
    reader = PdfReader(str(path))
    groups = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
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
        if not parsed.get("invoice_number"):
            parsed["notes"] += "; confirm invoice boundaries and number"
        results.append(parsed)
    return results
