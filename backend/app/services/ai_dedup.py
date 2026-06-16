"""AI-powered duplicate detection using OpenAI.

Strategy
--------
1. Fast pre-filter (no API cost) — exact barcode match or brand similarity ≥ 0.5
   narrows the full record set to a shortlist of plausible candidates.
   Exact barcode hits are returned immediately (certainty = 1.0).
2. OpenAI call — given the new record's extracted fields and the shortlist, the
   model decides which (if any) are the same physical product.
   This catches brand name variants, weight unit differences, OCR errors, and
   product line nuances that heuristics miss.
3. Falls back gracefully to an empty list if OpenAI is unavailable.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from app.config import settings
from app.schemas.imdb import MergeCandidate

if TYPE_CHECKING:
    from app.models import ItemRecord

logger = logging.getLogger(__name__)

_PRE_FILTER_BRAND_THRESHOLD = 0.50   # cheap fuzzy gate before calling OpenAI
_MAX_CANDIDATES = 15                  # cap prompt size / cost
_AI_CONFIDENCE_THRESHOLD = 0.70      # model must be ≥ this to flag as duplicate


# ── Response schema ───────────────────────────────────────────────────────────

class _DuplicateMatch(BaseModel):
    existing_record_id: int
    is_duplicate: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class _AIDedupResponse(BaseModel):
    matches: list[_DuplicateMatch] = Field(default_factory=list)


# ── Prompt builder ────────────────────────────────────────────────────────────

def _record_summary(r: "ItemRecord") -> dict:
    return {
        "id": r.id,
        "brand": r.brand,
        "item_name": r.item_name,
        "weight": r.weight,
        "packaging_type": r.packaging_type,
        "variant_type": r.variant_type,
        "barcode": r.barcode,
        "category_type": r.category_type,
        "country_of_origin": r.country_of_origin,
    }


_SYSTEM_PROMPT = (
    "You are a retail product catalog deduplication assistant. "
    "Decide whether any existing database records represent the same physical product "
    "as the newly extracted record. A product IS a duplicate when it is the same physical "
    "SKU — same brand, product line, size/weight, and variant. Two records are NOT duplicates "
    "when they differ in weight, variant (e.g. ORIGINAL vs DIET), or are different product "
    "lines from the same brand. Be conservative — prefer false negatives over false positives. "
    "Return a JSON object with a 'matches' array."
)

_USER_TEMPLATE = """\
Newly extracted product:
{new_product}

Existing database candidates:
{candidates}

For every candidate, set is_duplicate=true only when you are confident it is the same product.
Provide a confidence score (0.0–1.0) and a brief reason."""


# ── Pre-filter (fast, no API cost) ───────────────────────────────────────────

def _pre_filter(
    new_rec: "ItemRecord",
    existing: list["ItemRecord"],
) -> tuple[list["ItemRecord"], list[MergeCandidate]]:
    certain: list[MergeCandidate] = []
    candidates: list["ItemRecord"] = []

    for rec in existing:
        if new_rec.barcode and rec.barcode and new_rec.barcode == rec.barcode:
            keep_id = min(rec.id, new_rec.id)
            dup_id  = max(rec.id, new_rec.id)
            certain.append(MergeCandidate(
                record_id=dup_id, duplicate_of=keep_id, score=1.0,
                reason="Identical barcode", matched_fields=["barcode"],
            ))
            continue

        brand_score = fuzz.WRatio(new_rec.brand or "", rec.brand or "") / 100.0
        cat_match   = (
            new_rec.category_type and rec.category_type and
            new_rec.category_type.lower() == rec.category_type.lower()
        )
        if brand_score >= _PRE_FILTER_BRAND_THRESHOLD or cat_match:
            candidates.append(rec)

    candidates = candidates[:_MAX_CANDIDATES]
    return candidates, certain


# ── AI call ───────────────────────────────────────────────────────────────────

def _call_openai(new_rec: "ItemRecord", candidates: list["ItemRecord"]) -> list[MergeCandidate]:
    if not settings.openai_api_key and not settings.openrouter_api_key:
        logger.debug("No OpenAI/OpenRouter key set — skipping AI dedup")
        return []

    try:
        from openai import OpenAI
        if settings.openrouter_api_key:
            client = OpenAI(api_key=settings.openrouter_api_key, base_url="https://openrouter.ai/api/v1")
            model = settings.openrouter_model
        else:
            client = OpenAI(api_key=settings.openai_api_key)
            model = settings.openai_model

        user_msg = _USER_TEMPLATE.format(
            new_product=json.dumps(_record_summary(new_rec), indent=2),
            candidates=json.dumps([_record_summary(r) for r in candidates], indent=2),
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw = response.choices[0].message.content or "{}"
        ai_result = _AIDedupResponse.model_validate(json.loads(raw))
    except Exception as exc:
        logger.error("AI dedup OpenAI/OpenRouter call failed: %s", exc)
        return _call_gemini(new_rec, candidates)

    results: list[MergeCandidate] = []
    for match in ai_result.matches:
        if not match.is_duplicate or match.confidence < _AI_CONFIDENCE_THRESHOLD:
            continue
        keep_id = min(match.existing_record_id, new_rec.id)
        dup_id  = max(match.existing_record_id, new_rec.id)
        results.append(MergeCandidate(
            record_id=dup_id,
            duplicate_of=keep_id,
            score=round(match.confidence, 3),
            reason=match.reason,
            matched_fields=["ai_analysis"],
        ))

    return results


def _call_gemini(new_rec: "ItemRecord", candidates: list["ItemRecord"]) -> list[MergeCandidate]:
    if not settings.gemini_api_key:
        logger.debug("GEMINI_API_KEY not set — skipping Gemini dedup fallback")
        return []

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = _SYSTEM_PROMPT + "\n\n" + _USER_TEMPLATE.format(
            new_product=json.dumps(_record_summary(new_rec), indent=2),
            candidates=json.dumps([_record_summary(r) for r in candidates], indent=2),
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_AIDedupResponse,
            temperature=0.0,
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[prompt],
            config=config,
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, _AIDedupResponse):
            ai_result = parsed
        elif parsed is not None:
            ai_result = _AIDedupResponse.model_validate(parsed)
        else:
            ai_result = _AIDedupResponse.model_validate(json.loads(response.text))
    except Exception as exc:
        logger.error("AI dedup Gemini call failed: %s", exc)
        return []

    results: list[MergeCandidate] = []
    for match in ai_result.matches:
        if not match.is_duplicate or match.confidence < _AI_CONFIDENCE_THRESHOLD:
            continue
        keep_id = min(match.existing_record_id, new_rec.id)
        dup_id  = max(match.existing_record_id, new_rec.id)
        results.append(MergeCandidate(
            record_id=dup_id,
            duplicate_of=keep_id,
            score=round(match.confidence, 3),
            reason=match.reason,
            matched_fields=["ai_analysis"],
        ))

    return results


# ── Public API ────────────────────────────────────────────────────────────────

def check_duplicates(
    new_records: list["ItemRecord"],
    existing_records: list["ItemRecord"],
) -> list[MergeCandidate]:
    """Check each new record against existing ones using OpenAI. Returns
    deduplicated candidates sorted by score descending."""
    if not existing_records:
        return []

    seen: set[tuple[int, int]] = set()
    all_candidates: list[MergeCandidate] = []

    for new_rec in new_records:
        ai_candidates, certain = _pre_filter(new_rec, existing_records)

        for c in certain:
            key = (c.duplicate_of, c.record_id)
            if key not in seen:
                seen.add(key)
                all_candidates.append(c)

        if ai_candidates:
            for c in _call_openai(new_rec, ai_candidates):
                key = (c.duplicate_of, c.record_id)
                if key not in seen:
                    seen.add(key)
                    all_candidates.append(c)

    all_candidates.sort(key=lambda c: c.score, reverse=True)
    return all_candidates
