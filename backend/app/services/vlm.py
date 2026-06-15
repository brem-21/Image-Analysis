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

_PROMPT = """You are a product-catalog data extractor. Look at the product image and extract
the following attributes from any visible labels, packaging, and logos:

- manufacturer: the company that makes the product (full legal name if shown)
- brand: the brand name shown on the packaging
- weight_raw: the net weight/volume EXACTLY as printed (e.g. "250 g", "1.5L")
- packaging_type: container type (Bottle, Can, Sachet, Box, Pouch, Tub, Glass Jar, etc.)
- country_of_origin: country shown (e.g. "Made in ..."), else null
- category_type: high-level product category (e.g. Spreads, Condiments, Beverages)
- segment_type: market segment shown or implied on pack (e.g. Premium, Value, Economy, Mainstream), else null
- variant_type: the product variant (e.g. ORIGINAL, DIET, SALTED, UNSALTED, ZERO)
- fragrance_flavor: the flavour or fragrance (e.g. VANILLA, LEMON, SALTED MARGARINE)
- promotion: any promotional OFFER text (e.g. "20% EXTRA FREE", "BUY 1 GET 1"), else null
- addons: bundled add-ons or free gifts shown on the pack, else null
- tagline: marketing slogan / descriptor (e.g. "SPREAD FOR BREAD", "LOW FAT"), else null

Rules:
- If a field is not clearly visible, return null for it. Do NOT guess.
- Do NOT attempt to read the barcode number.
- Do NOT compose a full product/item name — only return the individual fields.
- For every field, include a confidence score from 0.0 to 1.0 in the
  "confidence" object keyed by the field name.
Return ONLY structured data matching the provided schema."""


class GeminiExtractor:
    def __init__(self) -> None:
        self._client = None

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
        # gemini-*-preview models commonly return 503 under load.
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
        else:  # pragma: no cover - loop always breaks or raises
            raise last_exc  # type: ignore[misc]

        # The SDK can return a parsed object; fall back to JSON text otherwise.
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, VLMExtraction):
            return parsed
        if parsed is not None:
            return VLMExtraction.model_validate(parsed)
        return VLMExtraction.model_validate(json.loads(response.text))


# Singleton; client is created lazily on first real extraction.
extractor = GeminiExtractor()
