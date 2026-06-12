"""Pydantic schemas for the 10 IMDB attributes and pipeline output."""
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


class IMDBAttributes(BaseModel):
    """The 10 IMDB columns. All optional — the pipeline fills what it can."""

    barcode: str | None = None
    category_type: str | None = None
    segment_type: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    product_name: str | None = None
    weight_value: float | None = None
    weight_unit: WeightUnit | None = None
    packaging_type: str | None = None
    country_of_origin: str | None = None
    promo_message: str | None = None


class VLMExtraction(BaseModel):
    """Schema Gemini Flash is constrained to return (9 soft fields + confidence).

    Barcode is excluded on purpose — it comes from the dedicated decoder.
    """

    category_type: str | None = None
    segment_type: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    product_name: str | None = None
    weight_raw: str | None = Field(None, description="Weight exactly as printed, e.g. '500 g', '1.5L'")
    packaging_type: str | None = None
    country_of_origin: str | None = None
    promo_message: str | None = None
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Per-field confidence 0..1 for each field above.",
    )


class RecordOut(IMDBAttributes):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None = None
    confidence: dict[str, float] = Field(default_factory=dict)
    source: dict[str, str] = Field(default_factory=dict)
    needs_review: bool = False
    created_at: datetime
    updated_at: datetime


class RecordUpdate(BaseModel):
    """Human edits from the preview screen. Any subset of the 10 fields."""

    barcode: str | None = None
    category_type: str | None = None
    segment_type: str | None = None
    manufacturer: str | None = None
    brand: str | None = None
    product_name: str | None = None
    weight_value: float | None = None
    weight_unit: WeightUnit | None = None
    packaging_type: str | None = None
    country_of_origin: str | None = None
    promo_message: str | None = None


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
