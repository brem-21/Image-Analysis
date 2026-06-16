"""OpenAI-compatible vision extraction (GPT-4o / OpenRouter).

A single class covers both direct OpenAI and OpenRouter — both expose the
same Chat Completions API; OpenRouter just needs a different base_url.
Uses JSON-object response mode so the prompt explicitly describes the expected
JSON structure; the result is validated into VLMExtraction.
"""
from __future__ import annotations

import base64
import json
import logging

from app.config import settings
from app.schemas.imdb import VLMExtraction

logger = logging.getLogger(__name__)

_PROMPT = """You are a product-catalog data extractor. Examine every part of the product image(s) carefully — front panel, back panel, side panels, bottom, any shelf/price tag at the bottom of the image, and all small print — then extract the fields below.

RULES:
1. Read what is actually printed on the packaging. Do NOT guess or infer from general product knowledge.
2. For each field, scan the entire image before giving up — the value may appear in small text, on a side panel, or on a tag.
3. Only return null when the information is genuinely absent from the image after a thorough look.
4. Set confidence 0.85–1.0 when the text is clearly legible; 0.5–0.84 when partially visible or small but readable; null when not found.

Return ONLY a valid JSON object with exactly these keys:

{
  "manufacturer": "full legal company name printed on pack, e.g. UPFIELD, NESTLE, GB FOODS",
  "brand": "brand name on the packaging, e.g. BLUE BAND, MAGGI, POMO",
  "weight_raw": "net weight/volume EXACTLY as printed including unit, e.g. '250G', '500ML', '1.5 KG'",
  "packaging_type": "physical container — uppercase, e.g. TUB, GLASS JAR, SACHET, BOTTLE, CAN, BOX, POUCH, TIN, WRAPPED",
  "country_of_origin": "country printed after 'Made in' or 'Product of' — strip the prefix; null if not on pack",
  "category_type": "shelf-tag product type — uppercase, e.g. MARGARINE, MAYONNAISE, BUTTER, POWDER, BEVERAGE, DETERGENT, TEABAG, TOMATO MIX, TOMATO PASTE, CHOCOLATE, SOAP, NOODLES",
  "segment_type": "market segment printed on pack, e.g. PREMIUM, VALUE, ECONOMY, MAINSTREAM; null if not stated",
  "variant_type": "product variant printed on pack, e.g. ORIGINAL, LOW FAT, SALTED, DIET, ZERO, 3 IN 1; null if not stated",
  "fragrance_flavor": "flavor or fragrance printed on pack, e.g. STRAWBERRY, LEMON, GINGER & GARLIC; null if not stated",
  "promotion": "on-pack promotional offer verbatim, e.g. '50% OFF', 'BUY 1 GET 1'; null if none",
  "addons": "bundled add-ons or free gifts printed on pack, e.g. 'SPOON INCLUDED'; null if none",
  "tagline": "marketing slogan or descriptor on pack, e.g. 'SPREAD FOR BREAD', 'CHOLESTEROL FREE'; null if none",
  "confidence": {
    "manufacturer": 0.0,
    "brand": 0.0,
    "weight_raw": 0.0,
    "packaging_type": 0.0,
    "country_of_origin": 0.0,
    "category_type": 0.0,
    "segment_type": 0.0,
    "variant_type": 0.0,
    "fragrance_flavor": 0.0,
    "promotion": 0.0,
    "addons": 0.0,
    "tagline": 0.0
  }
}

Do NOT read or transcribe the barcode number. Do NOT compose a full product name."""


class OpenAICompatibleExtractor:
    """Calls any OpenAI-compatible Chat Completions endpoint with vision."""

    def __init__(
        self,
        api_key_setting: str,
        model_setting: str,
        base_url: str | None = None,
        name: str = "openai",
    ) -> None:
        self._api_key_setting = api_key_setting
        self._model_setting = model_setting
        self._base_url = base_url
        self.name = name
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            api_key = getattr(settings, self._api_key_setting)
            if not api_key:
                raise RuntimeError(f"{self._api_key_setting.upper()} is not configured")
            kwargs: dict = {"api_key": api_key, "timeout": 60.0}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> VLMExtraction:
        client = self._get_client()
        model = getattr(settings, self._model_setting)

        image_b64 = base64.b64encode(image_bytes).decode()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        raw = response.choices[0].message.content or "{}"
        logger.debug("VLM raw response from %s: %.200s", self.name, raw)
        return VLMExtraction.model_validate(json.loads(raw))


# Singletons — clients are created lazily on first use.
openai_extractor = OpenAICompatibleExtractor(
    api_key_setting="openai_api_key",
    model_setting="openai_model",
    name="openai",
)

openrouter_extractor = OpenAICompatibleExtractor(
    api_key_setting="openrouter_api_key",
    model_setting="openrouter_model",
    base_url="https://openrouter.ai/api/v1",
    name="openrouter",
)
