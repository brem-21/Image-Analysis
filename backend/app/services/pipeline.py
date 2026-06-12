"""Orchestrates the hybrid extraction pipeline for a single image:

   preprocess -> barcode decode -> VLM extract -> external enrichment
              -> normalize -> confidence/needs_review

Returns a plain dict of column values + per-field confidence + source maps,
ready to be persisted as an ItemRecord.
"""
from __future__ import annotations

from app.config import settings
from app.services import barcode as barcode_svc
from app.services import enrichment, normalize, preprocess
from app.services.vlm import extractor

_VLM_FIELDS = (
    "category_type", "segment_type", "manufacturer", "brand",
    "product_name", "packaging_type", "country_of_origin", "promo_message",
)


def run_pipeline(image_bytes: bytes, use_vlm: bool = True, use_enrichment: bool = True) -> dict:
    values: dict = {}
    confidence: dict[str, float] = {}
    source: dict[str, str] = {}

    clean = preprocess.preprocess(image_bytes)

    # 1) Barcode — deterministic decoder, never the VLM.
    code, code_conf = barcode_svc.decode_barcode(clean)
    if code:
        values["barcode"] = code
        confidence["barcode"] = code_conf
        source["barcode"] = "barcode_decoder"

    # 2) VLM — soft fields with structured output + per-field confidence.
    if use_vlm:
        try:
            vlm = extractor.extract(clean, mime_type="image/jpeg")
            for f in _VLM_FIELDS:
                val = getattr(vlm, f, None)
                if val:
                    values[f] = val
                    confidence[f] = float(vlm.confidence.get(f, 0.5))
                    source[f] = "vlm"
            if vlm.weight_raw:
                wv, wu = normalize.parse_weight(vlm.weight_raw)
                if wv is not None:
                    values["weight_value"], values["weight_unit"] = wv, wu
                    confidence["weight_value"] = float(vlm.confidence.get("weight_raw", 0.5))
                    source["weight_value"] = "vlm"
        except Exception as exc:  # keep barcode result even if VLM fails
            values.setdefault("_vlm_error", str(exc))

    # 3) Enrichment — authoritative cross-check by validated barcode.
    if use_enrichment and barcode_svc.is_valid_barcode(values.get("barcode")):
        enriched = enrichment.lookup_barcode(values["barcode"])
        if enriched:
            for f, val in enriched.items():
                if f == "weight_raw":
                    wv, wu = normalize.parse_weight(val)
                    if wv is not None and values.get("weight_value") is None:
                        values["weight_value"], values["weight_unit"] = wv, wu
                        confidence["weight_value"] = 0.9
                        source["weight_value"] = "external_lookup"
                    continue
                # External data is authoritative; fill gaps and boost confidence.
                if not values.get(f) or confidence.get(f, 0) < 0.9:
                    values[f] = val
                    confidence[f] = 0.9
                    source[f] = "external_lookup"

    # 4) Normalization / canonicalization (centralized naming).
    for f in ("brand", "category_type", "segment_type", "packaging_type"):
        if values.get(f):
            values[f] = normalize.canonicalize(f, values[f])
    if values.get("country_of_origin"):
        values["country_of_origin"] = normalize.normalize_country(values["country_of_origin"])

    # 5) needs_review: flag if any present field is below threshold or barcode invalid.
    low_conf = any(c < settings.confidence_threshold for c in confidence.values())
    bad_barcode = bool(values.get("barcode")) and not barcode_svc.is_valid_barcode(values["barcode"])
    needs_review = low_conf or bad_barcode or not values.get("barcode")

    values.pop("_vlm_error", None)
    return {
        "values": values,
        "confidence": confidence,
        "source": source,
        "needs_review": needs_review,
    }
