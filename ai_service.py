"""Optional, user-triggered OpenAI assistance. Never posts accounting entries.

The key is read from SABER_AI_API_KEY or kept in memory for this app session.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-4.1-mini"


def _respond(content, api_key):
    if not api_key: raise ValueError("Enter an OpenAI API key to use AI assistance")
    payload = json.dumps({"model": MODEL, "store": False, "input": [{"role": "user", "content": content}]}).encode("utf-8")
    request = Request(API_URL, data=payload, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f"AI request failed (HTTP {exc.code}). Check the API key, model access, and billing.") from None
    except URLError:
        raise ValueError("AI service could not be reached. Check the internet connection.") from None
    texts = [part.get("text", "") for item in result.get("output", []) if item.get("type") == "message"
             for part in item.get("content", []) if part.get("type") == "output_text"]
    if not texts: raise ValueError("AI did not return a readable suggestion")
    value = "\n".join(texts).strip()
    if value.startswith("```"): value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try: return json.loads(value)
    except json.JSONDecodeError: raise ValueError("AI response could not be read. Please retry.") from None


def suggest_account(description, accounts, api_key):
    allowed = {str(row).split(" - ", 1)[0]: str(row).split(" - ", 1)[-1] for row in accounts}
    if not description.strip() or not allowed: raise ValueError("Enter an expense description and load the chart of accounts")
    candidates = [f"{code} - {name}" for code, name in allowed.items() if code.startswith("6") and len(code) == 9]
    if not candidates: raise ValueError("No 9-digit expense accounts are available")
    prompt = ("Suggest one account for this Lebanese expense. Return JSON only: "
              '{"code":"...","reason":"..."}. Choose only from these exact account codes; do not invent one. '
              f"Description: {description[:400]}\nAccounts: " + " | ".join(candidates[:160]))
    result = _respond([{"type": "input_text", "text": prompt}], api_key)
    code = str(result.get("code") or "").strip()
    if code not in allowed: raise ValueError("AI suggested an account outside the active chart; choose an account manually")
    return {"code": code, "name": allowed[code], "reason": str(result.get("reason") or "")[:300]}


def read_invoice_pdf(path, api_key):
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    source = Path(path)
    if source.suffix.lower() != ".pdf": raise ValueError("Choose a PDF invoice")
    reader = PdfReader(str(source))
    if not reader.pages: raise ValueError("This PDF has no pages")
    # One page per preview prevents accidentally combining multiple invoices.
    writer = PdfWriter(); writer.add_page(reader.pages[0]); stream = BytesIO(); writer.write(stream)
    raw = stream.getvalue()
    if len(raw) > 8_000_000: raise ValueError("First PDF page is too large for AI preview")
    encoded = base64.b64encode(raw).decode("ascii")
    prompt = ('Read only page 1. Return JSON only with keys invoice_number, invoice_date (DD-MM-YYYY), '
              'party_name (the billed customer or supplier), currency (USD/LBP/EUR/AED), subtotal, vat, total. '
              'Use null when a field is unclear; do not calculate missing VAT or invent values. One invoice only.')
    result = _respond([{"type": "input_file", "filename": "invoice-page-1.pdf", "file_data": "data:application/pdf;base64," + encoded},
                       {"type": "input_text", "text": prompt}], api_key)
    data = {key: result.get(key) for key in ("invoice_number", "invoice_date", "party_name", "currency", "subtotal", "vat", "total")}
    if data["currency"] not in (None, "USD", "LBP", "EUR", "AED"): data["currency"] = None
    for key in ("subtotal", "vat", "total"):
        if data[key] is not None:
            try: data[key] = float(str(data[key]).replace(",", ""))
            except ValueError: data[key] = None
    return data
