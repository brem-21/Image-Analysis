"""Orchestrates the hybrid extraction pipeline for a single image:

   preprocess -> barcode decode -> VLM extract -> external enrichment
              -> normalize -> generate ITEM_NAME -> confidence/needs_review

Returns a plain dict of field values + per-field confidence + source maps,
ready to be persisted as an ItemRecord.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.schemas.imdb import VLMExtraction
from app.services import barcode as barcode_svc
from app.services import enrichment, normalize, preprocess

logger = logging.getLogger(__name__)


def _vlm_extract(image_bytes: bytes) -> tuple[VLMExtraction, str | None]:
    """Try VLM providers in order: OpenRouter → OpenAI → Gemini.

    Returns the first successful result, or an empty VLMExtraction and the
    concatenated error string if all providers fail.
    """
    from app.services.vlm import extractor as gemini_extractor
    from app.services.vlm_openai import openai_extractor, openrouter_extractor

    candidates = []
    if settings.openrouter_api_key:
        candidates.append(openrouter_extractor)
    if settings.openai_api_key:
        candidates.append(openai_extractor)
    candidates.append(gemini_extractor)  # always included as final fallback

    errors: list[str] = []
    for ext in candidates:
        try:
            result = ext.extract(image_bytes, mime_type="image/jpeg")
            logger.info("VLM extraction succeeded via %s", ext.name)
            return result, None
        except Exception as exc:
            msg = f"{ext.name}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            logger.warning("VLM provider %s failed: %s", ext.name, exc)

    return VLMExtraction(), " | ".join(errors)

# Soft fields the VLM returns directly (excludes barcode, weight, item_name).
_VLM_FIELDS = (
    "manufacturer", "brand", "packaging_type", "country_of_origin",
    "category_type", "segment_type", "variant_type", "fragrance_flavor",
    "promotion", "addons", "tagline",
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
    vlm_error: str | None = None
    if use_vlm:
        vlm, vlm_error = _vlm_extract(clean)
        for f in _VLM_FIELDS:
            val = getattr(vlm, f, None)
            if val:
                values[f] = val
                confidence[f] = float(getattr(vlm.confidence, f, None) or 0.5)
                source[f] = "vlm"
        if vlm.weight_raw:
            wv, wu = normalize.parse_weight(vlm.weight_raw)
            if wv is not None:
                values["weight_value"], values["weight_unit"] = wv, wu
                confidence["weight_value"] = float(vlm.confidence.weight_raw or 0.5)
                source["weight_value"] = "vlm"

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
                if f not in _VLM_FIELDS:
                    continue
                # External data is authoritative; fill gaps and boost confidence.
                if not values.get(f) or confidence.get(f, 0) < 0.9:
                    values[f] = val
                    confidence[f] = 0.9
                    source[f] = "external_lookup"

    # 4) Normalization / canonicalization (centralized naming).
    for f in ("brand", "category_type", "segment_type", "variant_type", "packaging_type"):
        if values.get(f):
            values[f] = normalize.canonicalize(f, values[f])
    if values.get("country_of_origin"):
        values["country_of_origin"] = normalize.normalize_country(values["country_of_origin"])

    # 5) Generate the standardized ITEM_NAME from the normalized fields.
    item_name = normalize.build_item_name(values)
    if item_name:
        values["item_name"] = item_name
        # Confidence = mean of the fields that fed the name (proxy).
        contributing = [confidence[k] for k in ("brand", "weight_value", "packaging_type") if k in confidence]
        confidence["item_name"] = round(sum(contributing) / len(contributing), 3) if contributing else 0.5
        source["item_name"] = "generated"

    # 6) needs_review: flag if any present field is below threshold or barcode invalid/missing.
    low_conf = any(c < settings.confidence_threshold for c in confidence.values())
    bad_barcode = bool(values.get("barcode")) and not barcode_svc.is_valid_barcode(values["barcode"])
    needs_review = low_conf or bad_barcode or not values.get("barcode")

    return {
        "values": values,
        "confidence": confidence,
        "source": source,
        "needs_review": needs_review,
        "vlm_error": vlm_error,
    }
