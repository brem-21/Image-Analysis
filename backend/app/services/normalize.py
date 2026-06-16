"""Deterministic validation & normalization. Makes output search-ready,
collapses naming variants (centralized naming), and generates a consistent
ITEM_NAME from a fixed template."""
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


def format_weight(value: float | None, unit: str | None) -> str | None:
    """Render the single WEIGHT column, e.g. 250.0/'g' -> '250G'."""
    if value is None:
        return None
    num = int(value) if float(value).is_integer() else value
    return f"{num}{(unit or '').upper()}"


# --- Country of origin ----------------------------------------------------
_COUNTRY_ALIASES = {
    "prc": "China", "p.r.c": "China", "made in china": "China",
    "usa": "United States", "u.s.a": "United States", "us": "United States",
    "uk": "United Kingdom", "u.k": "United Kingdom", "great britain": "United Kingdom",
    "uae": "United Arab Emirates",
    "rsa": "South Africa",
    "gh": "Ghana", "made in ghana": "Ghana",
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


# --- Canonical naming -----------------------------------------------------
# Seed dictionaries; extend with the provided sample data. Fuzzy match collapses
# variants ("coca cola" / "Coca-Cola" / "COKE") -> one canonical label.
CANONICAL = {
    "brand": ["Coca-Cola", "Pepsi", "Nestle", "Unilever", "Blue Band", "Lele", "Indomie"],
    "category_type": ["Beverages", "Snacks", "Dairy", "Spreads", "Condiments", "Household", "Personal Care"],
    "segment_type": ["Premium", "Value", "Economy", "Mainstream", "Standard"],
    "variant_type": ["Original", "Diet", "Salted", "Unsalted", "Zero", "Light"],
    "packaging_type": ["Bottle", "Can", "Sachet", "Box", "Pouch", "Carton", "Jar", "Tub", "Glass Jar", "Tube"],
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


# --- ITEM_NAME generation -------------------------------------------------
# Fixed token order for the standardized item name. Tweak here to change the
# naming convention across every row. Empty/duplicate tokens are dropped.
ITEM_NAME_ORDER = (
    "brand", "weight", "packaging_type", "fragrance_flavor",
    "variant_type", "tagline", "category_type", "manufacturer",
)


def build_item_name(values: dict) -> str | None:
    """Compose a consistent uppercase ITEM_NAME from the record's fields."""
    weight_str = format_weight(values.get("weight_value"), values.get("weight_unit"))
    parts_source = {**values, "weight": weight_str}

    tokens: list[str] = []
    seen: set[str] = set()
    for key in ITEM_NAME_ORDER:
        val = parts_source.get(key)
        if not val:
            continue
        token = str(val).upper().strip()
        # Avoid repeating words already present (e.g. brand echoed in tagline).
        for word in token.split():
            if word not in seen:
                tokens.append(word)
                seen.add(word)
    name = " ".join(tokens).strip()
    return name or None
