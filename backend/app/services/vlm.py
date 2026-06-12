"""Gemini Flash vision extraction with structured JSON output.

We constrain the model to the VLMExtraction schema so it returns typed fields
plus per-field confidence — never free-form prose. Barcode is intentionally
excluded (handled by the dedicated decoder).
"""
from __future__ import annotations

import json

from app.config import settings
from app.schemas.imdb import VLMExtraction

_PROMPT = """You are a product-catalog data extractor. Look at the product image and extract
the following attributes from any visible labels, packaging, and logos:

- category_type: high-level product category (e.g. Beverages, Snacks, Dairy)
- segment_type: finer sub-category (e.g. Carbonated Drinks, Instant Noodles)
- manufacturer: the company that makes the product
- brand: the brand name shown on the packaging
- product_name: the specific product/variant name
- weight_raw: the net weight/volume EXACTLY as printed (e.g. "500 g", "1.5L")
- packaging_type: container type (Bottle, Can, Sachet, Box, Pouch, etc.)
- country_of_origin: country shown (e.g. "Made in ..."), else null
- promo_message: any promotional/marketing text on the pack, else null

Rules:
- If a field is not clearly visible, return null for it. Do NOT guess.
- Do NOT attempt to read the barcode number.
- For every field, include a confidence score from 0.0 to 1.0 in the
  "confidence" object keyed by the field name.
Return ONLY structured data matching the provided schema."""


class GeminiExtractor:
    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> VLMExtraction:
        from google.genai import types

        client = self._get_client()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VLMExtraction,
                temperature=0.0,
            ),
        )
        # The SDK can return a parsed object; fall back to JSON text otherwise.
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, VLMExtraction):
            return parsed
        if parsed is not None:
            return VLMExtraction.model_validate(parsed)
        return VLMExtraction.model_validate(json.loads(response.text))


# Singleton; client is created lazily on first real extraction.
extractor = GeminiExtractor()
