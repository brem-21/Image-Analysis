import asyncio
import logging
from functools import partial

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models import ExtractionSession, ItemRecord, User
from app.schemas.imdb import ExtractResponse, MergeCandidate, RecordOut
from app.services import ai_dedup
from app.services import storage as storage_svc
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract", tags=["extract"])

_MAX_BYTES = settings.max_upload_mb * 1024 * 1024


def _validate_uploads(files: list[UploadFile]) -> None:
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files uploaded.")
    if len(files) > settings.max_upload_files:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Too many files: {len(files)} (max {settings.max_upload_files} per request).",
        )
    allowed = settings.allowed_image_type_set
    for f in files:
        if (f.content_type or "").lower() not in allowed:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"Unsupported type for '{f.filename}': {f.content_type}. Allowed: {sorted(allowed)}.",
            )
        if f.size is not None and f.size > _MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"'{f.filename}' is {f.size // (1024 * 1024)}MB (max {settings.max_upload_mb}MB).",
            )


def _merge_results(results: list[dict]) -> dict:
    """Merge per-image pipeline results into one record.

    For each field, keeps the value with the highest confidence across all images.
    This way multiple angles of the same product complement each other — a front
    image might give brand/weight while a back image gives barcode/country.
    """
    if not results:
        return {"values": {}, "confidence": {}, "source": {}, "needs_review": True, "vlm_error": None}
    if len(results) == 1:
        return results[0]

    merged_values: dict = {}
    merged_confidence: dict = {}
    merged_source: dict = {}

    for r in results:
        for field, value in r.get("values", {}).items():
            if not value and value != 0:
                continue
            conf = r.get("confidence", {}).get(field, 0.5)
            if conf > merged_confidence.get(field, -1):
                merged_values[field] = value
                merged_confidence[field] = conf
                merged_source[field] = r.get("source", {}).get(field, "vlm")

    needs_review = any(r.get("needs_review", True) for r in results)
    errors = [r["vlm_error"] for r in results if r.get("vlm_error")]
    vlm_error = " | ".join(errors) if errors else None

    return {
        "values": merged_values,
        "confidence": merged_confidence,
        "source": merged_source,
        "needs_review": needs_review,
        "vlm_error": vlm_error,
    }


def _record_from_pipeline(result: dict, user_id: int, session_id: int, s3_key: str | None = None) -> ItemRecord:
    v = result["values"]
    return ItemRecord(
        user_id=user_id,
        session_id=session_id,
        item_name=v.get("item_name"),
        barcode=v.get("barcode"),
        manufacturer=v.get("manufacturer"),
        brand=v.get("brand"),
        weight_value=v.get("weight_value"),
        weight_unit=v.get("weight_unit"),
        packaging_type=v.get("packaging_type"),
        country_of_origin=v.get("country_of_origin"),
        category_type=v.get("category_type"),
        segment_type=v.get("segment_type"),
        variant_type=v.get("variant_type"),
        fragrance_flavor=v.get("fragrance_flavor"),
        promotion=v.get("promotion"),
        addons=v.get("addons"),
        tagline=v.get("tagline"),
        confidence=result["confidence"],
        source=result["source"],
        needs_review=result["needs_review"],
        s3_key=s3_key,
    )


@router.post("", response_model=ExtractResponse, status_code=status.HTTP_201_CREATED)
async def extract(
    files: list[UploadFile] = File(...),
    label: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractResponse:
    """Accept one or more product images (different angles of the same product),
    run the extraction pipeline on each, merge into a single IMDB record, and persist."""
    _validate_uploads(files)

    existing_records = list(db.scalars(select(ItemRecord)))

    batch = ExtractionSession(user_id=current_user.id, label=label)
    db.add(batch)
    db.flush()

    loop = asyncio.get_running_loop()

    per_image_results: list[dict] = []
    primary_s3_key: str | None = None  # S3 key of the first successfully uploaded image

    for f in files:
        image_bytes = await f.read()
        if len(image_bytes) > _MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"'{f.filename}' exceeds the {settings.max_upload_mb}MB limit.",
            )

        # Upload every angle to S3; use the first as the record's primary key.
        key = storage_svc.s3_key(current_user.id, batch.id, f.filename or "image.jpg")
        stored_key = await storage_svc.upload_image(key, image_bytes, f.content_type or "image/jpeg")
        if primary_s3_key is None:
            primary_s3_key = stored_key

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, partial(run_pipeline, image_bytes)),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            logger.error("Pipeline timed out for '%s'", f.filename)
            result = {
                "values": {}, "confidence": {}, "source": {},
                "needs_review": True, "vlm_error": f"Pipeline timed out for {f.filename}",
            }
        except Exception as exc:
            logger.error("Pipeline failed for '%s': %s", f.filename, exc)
            result = {
                "values": {}, "confidence": {}, "source": {},
                "needs_review": True, "vlm_error": f"{f.filename}: {type(exc).__name__}: {exc}",
            }

        per_image_results.append(result)

    # Merge all angle results into one record.
    merged = _merge_results(per_image_results)
    rec = _record_from_pipeline(merged, current_user.id, batch.id, s3_key=primary_s3_key)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    record_out = RecordOut.model_validate(rec)
    record_out.vlm_error = merged.get("vlm_error")

    try:
        dedup_candidates: list[MergeCandidate] = await asyncio.wait_for(
            loop.run_in_executor(None, partial(ai_dedup.check_duplicates, [rec], existing_records)),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        logger.warning("AI dedup timed out — returning empty candidates")
        dedup_candidates = []

    return ExtractResponse(session_id=batch.id, records=[record_out], dedup_candidates=dedup_candidates)
