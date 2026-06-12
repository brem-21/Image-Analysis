"""Deterministic validation & normalization. Makes output search-ready and
collapses naming variants (centralized naming criterion)."""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

# --- Weight parsing -------------------------------------------------------
_WEIGHT_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|g|mg|ml|l|oz|lb|lbs|liters?|grams?|kilograms?|pcs|pieces|x)?",
    re.IGNORECASE,
)

_UNIT_MAP = {
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "mg": "mg",
    "ml": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "oz": "oz",
    "lb": "lb", "lbs": "lb",
    "pcs": "unit", "pieces": "unit", "x": "unit",
}


def parse_weight(raw: str | None) -> tuple[float | None, str | None]:
    if not raw:
        return None, None
    m = _WEIGHT_RE.search(raw.strip())
    if not m:
        return None, None
    value = float(m.group("value").replace(",", "."))
    unit_token = (m.group("unit") or "").lower()
    unit = _UNIT_MAP.get(unit_token)
    return value, unit


# --- Country of origin ----------------------------------------------------
_COUNTRY_ALIASES = {
    "prc": "China", "p.r.c": "China", "made in china": "China",
    "usa": "United States", "u.s.a": "United States", "us": "United States",
    "uk": "United Kingdom", "u.k": "United Kingdom", "great britain": "United Kingdom",
    "uae": "United Arab Emirates",
    "rsa": "South Africa",
    "deutschland": "Germany",
}


def normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"^\s*made in\s*", "", raw.strip(), flags=re.IGNORECASE)
    key = cleaned.lower().strip(" .")
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    return cleaned.strip().title()


# --- Canonical naming (brand / category / segment / packaging) -----------
# Seed dictionaries; extend with the provided sample data. Fuzzy match collapses
# variants like "coca cola" / "Coca-Cola" / "COKE" -> one canonical label.
CANONICAL = {
    "brand": ["Coca-Cola", "Pepsi", "Nestle", "Unilever", "Cadbury", "Indomie"],
    "category_type": ["Beverages", "Snacks", "Dairy", "Household", "Personal Care", "Confectionery"],
    "segment_type": ["Carbonated Drinks", "Instant Noodles", "Chocolate", "Detergent", "Bottled Water"],
    "packaging_type": ["Bottle", "Can", "Sachet", "Box", "Pouch", "Carton", "Jar", "Tube"],
}

_FUZZY_THRESHOLD = 82


def canonicalize(field: str, value: str | None) -> str | None:
    if not value:
        return value
    choices = CANONICAL.get(field)
    if not choices:
        return value.strip()
    match = process.extractOne(value.strip(), choices, scorer=fuzz.WRatio)
    if match and match[1] >= _FUZZY_THRESHOLD:
        return match[0]
    return value.strip().title()
