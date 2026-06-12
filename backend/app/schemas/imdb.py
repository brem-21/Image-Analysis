"""Pydantic schemas for the IMDB attributes and pipeline output.

Target output columns (must match the product-master export exactly):
    ITEM_NAME, BARCODE, MANUFACTURER, BRAND, WEIGHT, PACKAGING_TYPE, COUNTRY,
    VARIANT_TYPE, FRAGRANCE_FLAVOR, PROMOTION, ADDONS, TAGLINE

Internally we also keep `category_type` plus per-field confidence/source for the
review UI. WEIGHT is stored split (value+unit) for dedup/templating and rendered
as a single string (e.g. "250G") on export.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class WeightUnit(str, Enum):
    g = "g"
    kg = "kg"
    mg = "mg"
    ml = "ml"
    l = "l"
    oz = "oz"
    lb = "lb"
    unit = "unit"  # count-based (e.g. "12 pcs")


# Internal field names (snake_case). ITEM_NAME is generated, not stored from VLM.
IMDB_FIELDS = (
    "item_name", "barcode", "manufacturer", "brand", "weight_value", "weight_unit",
    "packaging_type", "country_of_origin", "variant_type", "fragrance_flavor",
    "promotion", "addons", "tagline", "category_type",
)


class IMDBAttributes(BaseModel):
    """All product attributes. Optional — the pipeline fills what it can."""

    item_name: str | None = None
    barcode: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    weight_value: float | None = None
    weight_unit: WeightUnit | None = None
    packaging_type: str | None = None
    country_of_origin: str | None = None
    variant_type: str | None = None
    fragrance_flavor: str | None = None
    promotion: str | None = None
    addons: str | None = None
    tagline: str | None = None
    category_type: str | None = None  # internal extra (not in official export)


class FieldConfidence(BaseModel):
    """Per-field confidence (0..1). Fixed properties — Gemini structured output
    does NOT support open dicts (additionalProperties), so we can't use a dict."""

    manufacturer: float | None = None
    brand: float | None = None
    weight_raw: float | None = None
    packaging_type: float | None = None
    country_of_origin: float | None = None
    variant_type: float | None = None
    fragrance_flavor: float | None = None
    promotion: float | None = None
    addons: float | None = None
    tagline: float | None = None
    category_type: float | None = None


class VLMExtraction(BaseModel):
    """Schema Gemini Flash is constrained to return.

    Barcode is excluded (dedicated decoder). ITEM_NAME is excluded (generated
    from a template). Weight comes back raw, exactly as printed.
    """

    manufacturer: str | None = None
    brand: str | None = None
    weight_raw: str | None = Field(None, description="Weight/volume exactly as printed, e.g. '250 g', '1.5L'")
    packaging_type: str | None = None
    country_of_origin: str | None = None
    variant_type: str | None = Field(None, description="Product variant, e.g. ORIGINAL, DIET, SALTED")
    fragrance_flavor: str | None = Field(None, description="Flavour or fragrance, e.g. VANILLA, LEMON")
    promotion: str | None = Field(None, description="Promotional offer text, e.g. '20% EXTRA FREE'")
    addons: str | None = Field(None, description="Bundled add-ons / free gifts shown on pack")
    tagline: str | None = Field(None, description="Marketing slogan / descriptor, e.g. 'SPREAD FOR BREAD'")
    category_type: str | None = Field(None, description="High-level category, e.g. Spreads, Condiments")
    confidence: FieldConfidence = Field(default_factory=FieldConfidence)


class RecordOut(IMDBAttributes):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None = None
    weight: str | None = None  # rendered "250G" form for display
    confidence: dict[str, float] = Field(default_factory=dict)
    source: dict[str, str] = Field(default_factory=dict)
    needs_review: bool = False
    created_at: datetime
    updated_at: datetime


class RecordUpdate(BaseModel):
    """Human edits from the preview screen. Any subset of fields."""

    item_name: str | None = None
    barcode: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    weight_value: float | None = None
    weight_unit: WeightUnit | None = None
    packaging_type: str | None = None
    country_of_origin: str | None = None
    variant_type: str | None = None
    fragrance_flavor: str | None = None
    promotion: str | None = None
    addons: str | None = None
    tagline: str | None = None
    category_type: str | None = None


class ExtractResponse(BaseModel):
    session_id: int
    records: list[RecordOut]


class MergeCandidate(BaseModel):
    record_id: int
    duplicate_of: int
    score: float
    reason: str
    matched_fields: list[str]


class DedupResponse(BaseModel):
    candidates: list[MergeCandidate]


class MergeRequest(BaseModel):
    keep_id: int
    merge_id: int
