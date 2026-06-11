"""Barcode-based enrichment via Open Food Facts (free, no API key).

Once we have a validated barcode we can fetch authoritative product data to
cross-check / fill brand, product name, country, and weight. Big accuracy win.
"""
from __future__ import annotations

import httpx

from app.config import settings


def lookup_barcode(barcode: str, timeout: float = 6.0) -> dict | None:
    """Return a partial attribute dict from Open Food Facts, or None."""
    url = f"{settings.off_api_base}/api/v2/product/{barcode}.json"
    try:
        resp = httpx.get(url, timeout=timeout, headers={"User-Agent": "GDSS-IMDB-Tool/1.0"})
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    if data.get("status") != 1:
        return None

    p = data.get("product", {})
    result: dict = {}
    if p.get("brands"):
        result["brand"] = p["brands"].split(",")[0].strip()
    if p.get("product_name"):
        result["product_name"] = p["product_name"].strip()
    if p.get("categories"):
        result["category_type"] = p["categories"].split(",")[-1].strip()
    if p.get("countries"):
        result["country_of_origin"] = p["countries"].split(",")[0].strip()
    if p.get("quantity"):
        result["weight_raw"] = p["quantity"].strip()
    if p.get("packaging"):
        result["packaging_type"] = p["packaging"].split(",")[0].strip()
    return result or None
