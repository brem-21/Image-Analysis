"""Gemini Flash vision extraction with structured JSON output.

We constrain the model to the VLMExtraction schema so it returns typed fields
plus per-field confidence — never free-form prose. Barcode is intentionally
excluded (handled by the dedicated decoder).
"""
from __future__ import annotations

import json
import logging
import time

from app.config import settings
from app.schemas.imdb import VLMExtraction

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BASE_DELAY = 1.5  # seconds; exponential backoff: 1.5, 3, 6, ...

_PROMPT = """You are a product-catalog data extractor. Look at the product image(s) — including any text tag/label at the bottom of the image — and extract the following attributes from visible labels, packaging, and logos.

Fields to extract:
- manufacturer: full legal company name that manufactures the product (e.g. UPFIELD, NESTLE, GB FOODS)
- brand: brand name shown on the packaging (e.g. BLUE BAND, MAGGI, POMO)
- weight_raw: net weight or net volume EXACTLY as printed, including unit (e.g. "250G", "500ML", "1.5 KG")
- packaging_type: physical container form — use uppercase short form (e.g. TUB, GLASS JAR, SACHET, BOTTLE, CAN, BOX, POUCH, TIN, WRAPPED)
- country_of_origin: country shown as "Made in …" or "Product of …" — strip the prefix; else null
- category_type: short product type descriptor as would appear on a shelf tag — use uppercase (e.g. MARGARINE, MAYONNAISE, BUTTER, POWDER, NOODLES, BEVERAGE, DETERGENT, TEABAG, TOMATO MIX, TOMATO PASTE, CHOCOLATE, SOAP)
- segment_type: market segment if clearly indicated on pack (e.g. PREMIUM, VALUE, ECONOMY, MAINSTREAM); else null
- variant_type: product variant if shown (e.g. ORIGINAL, LOW FAT, SALTED, DIET, ZERO, 3 IN 1); else null
- fragrance_flavor: flavor or fragrance if shown (e.g. STRAWBERRY, LEMON, ORANGE, VANILLA, RICH, GINGER & GARLIC); else null
- promotion: on-pack promotional offer text verbatim (e.g. "50% OFF", "BUY 1 GET 1", "20% EXTRA FREE"); else null
- addons: bundled add-ons or free gifts shown on pack (e.g. "SPOON INCLUDED", "5 FREE ENVELOPE"); else null
- tagline: marketing slogan or descriptor (e.g. "SPREAD FOR BREAD", "LOW FAT", "CHOLESTEROL FREE"); else null

Rules:
- If a field is not clearly visible, return null. Do NOT guess.
- Do NOT read or transcribe the barcode number.
- Do NOT compose a full product/item name — return only the individual fields above.
- For every field include a confidence score 0.0–1.0 in the "confidence" object keyed by the field name.
Return ONLY structured data matching the provided schema."""


class GeminiExtractor:
    def __init__(self) -> None:
        self._client = None
        self.name = "gemini"

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            try:
                http_options = types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000))
                self._client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)
            except Exception:  # older SDKs may not support http_options timeout
                self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> VLMExtraction:
        from google.genai import types
        from google.genai import errors as genai_errors

        client = self._get_client()
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VLMExtraction,
            temperature=0.0,
        )
        contents = [types.Part.from_bytes(data=image_bytes, mime_type=mime_type), _PROMPT]

        # Retry transient overload/rate-limit errors (503/429) with backoff.
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_model, contents=contents, config=config,
                )
                break
            except (genai_errors.ServerError, genai_errors.ClientError) as exc:
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if status not in (429, 500, 503) or attempt == _MAX_RETRIES - 1:
                    raise
                last_exc = exc
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning("Gemini %s on attempt %d/%d; retrying in %.1fs",
                               status, attempt + 1, _MAX_RETRIES, delay)
                time.sleep(delay)
        else:  # pragma: no cover
            raise last_exc  # type: ignore[misc]

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, VLMExtraction):
            return parsed
        if parsed is not None:
            return VLMExtraction.model_validate(parsed)
        return VLMExtraction.model_validate(json.loads(response.text))


# Singleton; client is created lazily on first real extraction.
extractor = GeminiExtractor()
