"""Non-blocking duplicate-name suggestions for customer and supplier entry."""

from difflib import SequenceMatcher
import unicodedata


_ARABIC_VARIANTS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه",
})


def normalize_party_name(name):
    text = unicodedata.normalize("NFKC", str(name or "")).casefold().translate(_ARABIC_VARIANTS)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn" and char != "ـ")
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


def similar_parties(name, parties, exclude_id=None, threshold=0.90):
    """Return existing parties whose normalized names are at least threshold similar."""
    wanted = normalize_party_name(name)
    if not wanted:
        return []
    matches = []
    for party in parties:
        if exclude_id is not None and str(party.get("id")) == str(exclude_id):
            continue
        existing = normalize_party_name(party.get("name"))
        if not existing:
            continue
        similarity = SequenceMatcher(None, wanted, existing).ratio()
        if similarity >= threshold:
            matches.append({
                "id": party.get("id"),
                "name": party["name"],
                "kind": party.get("kind") or "",
                "account_number": party.get("account_number") or "",
                "similarity": similarity,
                "exact": wanted == existing,
            })
    return sorted(matches, key=lambda party: (-party["similarity"], party["name"]))