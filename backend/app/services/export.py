"""Export records to CSV / Excel.

Column names and order match the ground-truth submission format:
    RECORD_ID, SESSION_ID,
    ITEM_NAME, BARCODE, MANUFACTURER, BRAND, WEIGHT, PACKAGING TYPE, COUNTRY,
    VARIANT, TYPE, FRAGRANCE_FLAVOR, PROMOTION, ADDONS, TAGLINE,
    SEGMENT_TYPE (extra, not in the 13 required ground-truth columns),
    NEEDS_REVIEW, UPLOADED_AT
"""
from __future__ import annotations

import io

import pandas as pd

from app.models import ItemRecord
from app.services.normalize import format_weight

# (export header, record attribute). WEIGHT is computed via "_weight" sentinel.
# Headers must match the ground-truth column names exactly.
ALL_COLUMNS: list[tuple[str, str]] = [
    ("RECORD_ID",        "id"),
    ("SESSION_ID",       "session_id"),
    ("ITEM_NAME",        "item_name"),
    ("BARCODE",          "barcode"),
    ("MANUFACTURER",     "manufacturer"),
    ("BRAND",            "brand"),
    ("WEIGHT",           "_weight"),
    ("PACKAGING TYPE",   "packaging_type"),   # space, not underscore (ground truth)
    ("COUNTRY",          "country_of_origin"),
    ("VARIANT",          "variant_type"),     # ground-truth column name
    ("TYPE",             "category_type"),    # ground-truth column name
    ("FRAGRANCE_FLAVOR", "fragrance_flavor"),
    ("PROMOTION",        "promotion"),
    ("ADDONS",           "addons"),
    ("TAGLINE",          "tagline"),
    ("SEGMENT_TYPE",     "segment_type"),     # extra — not in the 13 required columns
    ("NEEDS_REVIEW",     "needs_review"),
    ("UPLOADED_AT",      "created_at"),
]

# Keep these names exported for any callers that still reference them.
OFFICIAL_COLUMNS = ALL_COLUMNS
META_COLUMNS: list[tuple[str, str]] = []


def _value(rec: ItemRecord, attr: str):
    if attr == "_weight":
        return format_weight(rec.weight_value, rec.weight_unit)
    val = getattr(rec, attr)
    # Render datetime as an ISO string so pandas doesn't add timezone noise.
    if hasattr(val, "isoformat"):
        return val.isoformat(timespec="seconds")
    return val


ALL_COLUMN_HEADERS: list[str] = [h for h, _ in ALL_COLUMNS]
_COLUMN_MAP: dict[str, str] = dict(ALL_COLUMNS)


def _resolve_columns(columns: list[str] | None) -> list[tuple[str, str]]:
    """Return the (header, attr) pairs to include, preserving ALL_COLUMNS order."""
    if not columns:
        return ALL_COLUMNS
    requested = {c.upper() for c in columns}
    return [(h, a) for h, a in ALL_COLUMNS if h in requested]


def _dataframe(records: list[ItemRecord], columns: list[str] | None = None) -> pd.DataFrame:
    cols = _resolve_columns(columns)
    headers = [h for h, _ in cols]
    rows = [{h: _value(r, attr) for h, attr in cols} for r in records]
    return pd.DataFrame(rows, columns=headers)


def to_csv(records: list[ItemRecord], columns: list[str] | None = None, include_meta: bool = False) -> bytes:
    return _dataframe(records, columns).to_csv(index=False).encode("utf-8")


def to_xlsx(records: list[ItemRecord], columns: list[str] | None = None, include_meta: bool = False) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _dataframe(records, columns).to_excel(writer, index=False, sheet_name="IMDB")
    return buf.getvalue()
