"""Export user records to a product-master CSV / Excel file.

Column headers and order match the required product-master format exactly:
    ITEM_NAME, BARCODE, MANUFACTURER, BRAND, WEIGHT, PACKAGING_TYPE, COUNTRY,
    CATEGORY_TYPE, SEGMENT_TYPE, VARIANT_TYPE, FRAGRANCE_FLAVOR,
    PROMOTION, ADDONS, TAGLINE

With include_meta=True we append NEEDS_REVIEW after the official columns.
"""
from __future__ import annotations

import io

import pandas as pd

from app.models import ItemRecord
from app.services.normalize import format_weight

# (export header, record attribute). WEIGHT is computed, not a direct attribute.
OFFICIAL_COLUMNS: list[tuple[str, str]] = [
    ("ITEM_NAME", "item_name"),
    ("BARCODE", "barcode"),
    ("MANUFACTURER", "manufacturer"),
    ("BRAND", "brand"),
    ("WEIGHT", "_weight"),
    ("PACKAGING_TYPE", "packaging_type"),
    ("COUNTRY", "country_of_origin"),
    ("CATEGORY_TYPE", "category_type"),
    ("SEGMENT_TYPE", "segment_type"),
    ("VARIANT_TYPE", "variant_type"),
    ("FRAGRANCE_FLAVOR", "fragrance_flavor"),
    ("PROMOTION", "promotion"),
    ("ADDONS", "addons"),
    ("TAGLINE", "tagline"),
]

META_COLUMNS: list[tuple[str, str]] = [
    ("NEEDS_REVIEW", "needs_review"),
]


def _value(rec: ItemRecord, attr: str):
    if attr == "_weight":
        return format_weight(rec.weight_value, rec.weight_unit)
    return getattr(rec, attr)


def _dataframe(records: list[ItemRecord], include_meta: bool) -> pd.DataFrame:
    columns = OFFICIAL_COLUMNS + (META_COLUMNS if include_meta else [])
    headers = [h for h, _ in columns]
    rows = [{h: _value(r, attr) for h, attr in columns} for r in records]
    return pd.DataFrame(rows, columns=headers)


def to_csv(records: list[ItemRecord], include_meta: bool = False) -> bytes:
    return _dataframe(records, include_meta).to_csv(index=False).encode("utf-8")


def to_xlsx(records: list[ItemRecord], include_meta: bool = False) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _dataframe(records, include_meta).to_excel(writer, index=False, sheet_name="IMDB")
    return buf.getvalue()
