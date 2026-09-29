"""Local expense account suggestions from the installed Lebanese chart.

Suggestions are advisory; the accountant selects and verifies the final account.
No API key or external service is required.
"""
from difflib import SequenceMatcher
import re

from lebanese_accounts import LEBANESE_ACCOUNTS


def suggest_account(expense_description, accounts=None):
    query = str(expense_description or "").strip().casefold()
    if not query:
        return None
    words = set(re.findall(r"\w+", query))
    candidates = []
    if accounts is None:
        accounts = [(row[0], row[1], row[2], row[3]) for row in LEBANESE_ACCOUNTS]
    else:
        accounts = [(str(row).split(" - ", 1)[0], str(row).split(" - ", 1)[-1], "", "") for row in accounts]
    for code, english, arabic, french in accounts:
        code = str(code)
        if not code.startswith("6") or len(code) < 4 or not code.isdigit():
            continue
        names = " ".join(str(name or "") for name in (english, arabic, french)).casefold()
        tokens = set(re.findall(r"\w+", names))
        overlap = len(words & tokens) / max(1, len(words))
        similarity = max(SequenceMatcher(None, query, str(name or "").casefold()).ratio()
                         for name in (english, arabic, french))
        score = max(overlap, similarity)
        candidates.append((score, len(code), code, english))
    if not candidates:
        return None
    score, _, code, name = max(candidates)
    if score < 0.35:
        return None
    return {"code": code, "name": name, "confidence": round(score, 2)}
