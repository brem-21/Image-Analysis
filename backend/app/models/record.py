from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ItemRecord(Base):
    """One product-master row: the 10 IMDB attributes plus pipeline metadata."""

    __tablename__ = "records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), index=True, nullable=True)

    # --- The 10 IMDB attributes ---
    barcode: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    category_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    segment_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    weight_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    packaging_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promo_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # --- Pipeline metadata (per-field) ---
    confidence: Mapped[dict] = mapped_column(JSON, default=dict)  # {field: 0..1}
    source: Mapped[dict] = mapped_column(JSON, default=dict)      # {field: "vlm"|"barcode_decoder"|...}
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="records")
    session = relationship("ExtractionSession", back_populates="records")

    IMDB_FIELDS = (
        "barcode", "category_type", "segment_type", "manufacturer", "brand",
        "product_name", "weight_value", "weight_unit", "packaging_type",
        "country_of_origin", "promo_message",
    )
