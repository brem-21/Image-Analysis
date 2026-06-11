from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import ExtractionSession, ItemRecord, User
from app.schemas.imdb import ExtractResponse, RecordOut
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/extract", tags=["extract"])


def _record_from_pipeline(result: dict, user_id: int, session_id: int) -> ItemRecord:
    v = result["values"]
    return ItemRecord(
        user_id=user_id,
        session_id=session_id,
        barcode=v.get("barcode"),
        category_type=v.get("category_type"),
        segment_type=v.get("segment_type"),
        manufacturer=v.get("manufacturer"),
        brand=v.get("brand"),
        product_name=v.get("product_name"),
        weight_value=v.get("weight_value"),
        weight_unit=v.get("weight_unit"),
        packaging_type=v.get("packaging_type"),
        country_of_origin=v.get("country_of_origin"),
        promo_message=v.get("promo_message"),
        confidence=result["confidence"],
        source=result["source"],
        needs_review=result["needs_review"],
    )


@router.post("", response_model=ExtractResponse, status_code=status.HTTP_201_CREATED)
async def extract(
    files: list[UploadFile] = File(...),
    label: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractResponse:
    """Accept one or more product images, run the hybrid pipeline, and persist
    one IMDB record per image (scoped to the current user + this batch)."""
    batch = ExtractionSession(user_id=current_user.id, label=label)
    db.add(batch)
    db.flush()  # assign batch.id

    records: list[ItemRecord] = []
    for f in files:
        image_bytes = await f.read()
        result = run_pipeline(image_bytes)
        rec = _record_from_pipeline(result, current_user.id, batch.id)
        db.add(rec)
        records.append(rec)

    db.commit()
    for rec in records:
        db.refresh(rec)

    return ExtractResponse(
        session_id=batch.id,
        records=[RecordOut.model_validate(r) for r in records],
    )
