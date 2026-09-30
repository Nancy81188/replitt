"""Free local invoice assistance. No API key, cloud request or paid service."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pdf_import import _parse_invoice_text
from ai_mapper import suggest_account as _local_suggest


def suggest_account(description, accounts, api_key=None):
    result = _local_suggest(description, accounts)
    if not result:
        raise ValueError("No reliable account suggestion. Choose the account manually.")
    return {**result, "reason": f"Local chart match ({result['confidence']:.0%}); verify before saving."}


def _tesseract():
    found = shutil.which("tesseract")
    if found: return found
    for base in (Path("C:/Program Files/Tesseract-OCR"), Path("C:/Program Files (x86)/Tesseract-OCR")):
        candidate = base / "tesseract.exe"
        if candidate.is_file(): return str(candidate)
    return None


def _ocr_page(page):
    exe = _tesseract()
    if not exe:
        raise ValueError("Scanned PDF: install the free Tesseract OCR for Windows (English, French and Arabic language data), then retry. Text PDFs work without it.")
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("Local PDF renderer is missing; update the Saber installer.") from exc
    with tempfile.TemporaryDirectory(prefix="saber-ocr-") as folder:
        image = Path(folder) / "page.png"
        page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(str(image))
        result = subprocess.run([exe, str(image), "stdout", "-l", "eng+fra+ara", "--psm", "6"],
                                capture_output=True, text=True, timeout=90, check=False)
        if result.returncode:
            # Some installations omit language packs; English is a usable fallback.
            result = subprocess.run([exe, str(image), "stdout", "-l", "eng", "--psm", "6"],
                                    capture_output=True, text=True, timeout=90, check=False)
        if result.returncode: raise ValueError("Local OCR failed: " + result.stderr.strip()[:240])
        return result.stdout


def read_invoice_pdf(path, api_key=None):
    """Read page one locally; never post or create entries without a reviewed Save."""
    from pypdf import PdfReader
    source = Path(path)
    if source.suffix.lower() != ".pdf": raise ValueError("Choose a PDF invoice")
    reader = PdfReader(str(source))
    if not reader.pages: raise ValueError("This PDF has no pages")
    text = reader.pages[0].extract_text() or ""
    if len(text.strip()) < 20:
        import fitz
        with fitz.open(str(source)) as document:
            text = _ocr_page(document[0])
    data = _parse_invoice_text(source, text)
    if not data.get("invoice_date") or not data.get("total"):
        data["notes"] += "; correct missing fields before saving"
    return data
