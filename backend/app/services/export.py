"""Export user records to a product-master CSV / Excel file (one row per
product, one column per IMDB attribute)."""
from __future__ import annotations

import io

import pandas as pd

from app.models import ItemRecord

EXPORT_COLUMNS = [
    "barcode", "category_type", "segment_type", "manufacturer", "brand",
    "product_name", "weight_value", "weight_unit", "packaging_type",
    "country_of_origin", "promo_message", "needs_review",
]


def _to_rows(records: list[ItemRecord]) -> list[dict]:
    return [{col: getattr(r, col) for col in EXPORT_COLUMNS} for r in records]


def to_csv(records: list[ItemRecord]) -> bytes:
    df = pd.DataFrame(_to_rows(records), columns=EXPORT_COLUMNS)
    return df.to_csv(index=False).encode("utf-8")


def to_xlsx(records: list[ItemRecord]) -> bytes:
    df = pd.DataFrame(_to_rows(records), columns=EXPORT_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="IMDB")
    return buf.getvalue()
