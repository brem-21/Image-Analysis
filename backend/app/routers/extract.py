from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models import ExtractionSession, ItemRecord, User
from sqlalchemy import select
from app.schemas.imdb import ExtractResponse, MergeCandidate, RecordOut
from app.services.pipeline import run_pipeline
from app.services import storage as storage_svc
from app.services import ai_dedup

router = APIRouter(prefix="/extract", tags=["extract"])

_MAX_BYTES = settings.max_upload_mb * 1024 * 1024


def _validate_uploads(files: list[UploadFile]) -> None:
    """Guard against abuse / runaway cost — each image is a paid VLM call."""
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
        # starlette populates .size when the client sends Content-Length.
        if f.size is not None and f.size > _MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"'{f.filename}' is {f.size // (1024 * 1024)}MB (max {settings.max_upload_mb}MB).",
            )


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
        variant_type=v.get("variant_type"),
        fragrance_flavor=v.get("fragrance_flavor"),
        promotion=v.get("promotion"),
        addons=v.get("addons"),
        tagline=v.get("tagline"),
        category_type=v.get("category_type"),
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
    """Accept one or more product images, run the hybrid pipeline, and persist
    one IMDB record per image (scoped to the current user + this batch)."""
    _validate_uploads(files)

    # Snapshot existing records BEFORE this batch so AI dedup only compares against them.
    existing_records = list(db.scalars(select(ItemRecord)))

    batch = ExtractionSession(user_id=current_user.id, label=label)
    db.add(batch)
    db.flush()  # assign batch.id

    # Keep each persisted record paired with its (transient) VLM error.
    pairs: list[tuple[ItemRecord, str | None]] = []
    for f in files:
        image_bytes = await f.read()
        if len(image_bytes) > _MAX_BYTES:  # fallback when Content-Length was absent
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"'{f.filename}' exceeds the {settings.max_upload_mb}MB limit.",
            )

        # Upload original image to S3 (non-blocking; extraction proceeds even on failure)
        key = storage_svc.s3_key(current_user.id, batch.id, f.filename or "image.jpg")
        stored_key = await storage_svc.upload_image(key, image_bytes, f.content_type or "image/jpeg")

        result = run_pipeline(image_bytes)
        rec = _record_from_pipeline(result, current_user.id, batch.id, s3_key=stored_key)
        db.add(rec)
        pairs.append((rec, result.get("vlm_error")))

    db.commit()

    new_records = [rec for rec, _ in pairs]
    out: list[RecordOut] = []
    for rec, vlm_error in pairs:
        db.refresh(rec)
        record_out = RecordOut.model_validate(rec)
        record_out.vlm_error = vlm_error
        out.append(record_out)

    # Ask Gemini whether any new records match something already in the database.
    dedup_candidates: list[MergeCandidate] = ai_dedup.check_duplicates(new_records, existing_records)

    return ExtractResponse(session_id=batch.id, records=out, dedup_candidates=dedup_candidates)
