from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ItemRecord(Base):
    """One product-master row.

    Official export columns map from these fields (see services/export.py).
    Weight is stored split (value+unit); WEIGHT is rendered on export.
    `category_type`, confidence, source and needs_review are internal extras.
    """

    __tablename__ = "records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), index=True, nullable=True)

    # --- Product attributes ---
    item_name: Mapped[str | None] = mapped_column(String(512), nullable=True)  # generated
    barcode: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    weight_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    packaging_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    variant_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fragrance_flavor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promotion: Mapped[str | None] = mapped_column(String(512), nullable=True)
    addons: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category_type: Mapped[str | None] = mapped_column(String(128), nullable=True)  # internal extra

    # --- Pipeline metadata (per-field) ---
    # MutableDict so in-place edits (e.g. on PATCH/merge) are tracked & persisted.
    confidence: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)  # {field: 0..1}
    source: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)      # {field: "vlm"|...}
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="records")
    session = relationship("ExtractionSession", back_populates="records")

    @property
    def weight(self) -> str | None:
        """Single rendered WEIGHT string, e.g. '250G'."""
        from app.services.normalize import format_weight

        return format_weight(self.weight_value, self.weight_unit)

    IMDB_FIELDS = (
        "item_name", "barcode", "manufacturer", "brand", "weight_value", "weight_unit",
        "packaging_type", "country_of_origin", "variant_type", "fragrance_flavor",
        "promotion", "addons", "tagline", "category_type",
    )
