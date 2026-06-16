from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models import ItemRecord, User
from app.schemas.imdb import (
    DedupResponse,
    MergeRequest,
    RecordOut,
    RecordUpdate,
)
from app.services import dedup

router = APIRouter(prefix="/records", tags=["records"])


def _owned_records(db: Session, user_id: int) -> list[ItemRecord]:
    return list(db.scalars(select(ItemRecord).where(ItemRecord.user_id == user_id)))


def _get_owned(db: Session, user_id: int, record_id: int) -> ItemRecord:
    rec = db.get(ItemRecord, record_id)
    if rec is None or rec.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return rec


@router.get("", response_model=list[RecordOut])
def list_records(
    response: Response,
    brand: str | None = Query(None),
    category_type: str | None = Query(None),
    segment_type: str | None = Query(None),
    packaging_type: str | None = Query(None),
    needs_review: bool | None = Query(None),
    session_id: int | None = Query(None),
    limit: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ItemRecord]:
    filters = []
    if brand:
        filters.append(ItemRecord.brand == brand)
    if category_type:
        filters.append(ItemRecord.category_type == category_type)
    if segment_type:
        filters.append(ItemRecord.segment_type == segment_type)
    if packaging_type:
        filters.append(ItemRecord.packaging_type == packaging_type)
    if needs_review is not None:
        filters.append(ItemRecord.needs_review == needs_review)
    if session_id is not None:
        filters.append(ItemRecord.session_id == session_id)

    base = select(ItemRecord)
    if filters:
        base = base.where(*filters)
    total = db.scalar(select(func.count()).select_from(ItemRecord).where(*filters) if filters else select(func.count()).select_from(ItemRecord)) or 0
    response.headers["X-Total-Count"] = str(total)

    stmt = base.order_by(ItemRecord.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.patch("/{record_id}", response_model=RecordOut)
def update_record(
    record_id: int,
    payload: RecordUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemRecord:
    rec = _get_owned(db, current_user.id, record_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rec, field, value.value if hasattr(value, "value") else value)
        rec.confidence[field] = 1.0  # human edit
        rec.source[field] = "human"

    # Regenerate ITEM_NAME from contributing fields unless the user set it directly.
    if "item_name" not in updates:
        from app.services.normalize import build_item_name

        regenerated = build_item_name({f: getattr(rec, f) for f in ItemRecord.IMDB_FIELDS})
        if regenerated:
            rec.item_name = regenerated
            rec.source["item_name"] = "generated"

    # Re-evaluate review flag now that a human has touched fields.
    rec.needs_review = any(c < 0.7 for c in rec.confidence.values())
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    rec = _get_owned(db, current_user.id, record_id)
    db.delete(rec)
    db.commit()


@router.post("/dedup", response_model=DedupResponse)
def dedup_records(
    session_id: int | None = Query(None, description="Limit dedup to one batch"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DedupResponse:
    records = _owned_records(db, current_user.id)
    if session_id is not None:
        records = [r for r in records if r.session_id == session_id]
    return DedupResponse(candidates=dedup.find_duplicates(records))


@router.post("/merge", response_model=RecordOut)
def merge_records(
    payload: MergeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemRecord:
    keep = _get_owned(db, current_user.id, payload.keep_id)
    merge = _get_owned(db, current_user.id, payload.merge_id)
    if keep.id == merge.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot merge a record into itself")

    # Fill gaps on the kept record from the merged one, preferring higher confidence.
    for field in ItemRecord.IMDB_FIELDS:
        keep_val = getattr(keep, field)
        merge_val = getattr(merge, field)
        if merge_val is None:
            continue
        keep_conf = keep.confidence.get(field, 0.0)
        merge_conf = merge.confidence.get(field, 0.0)
        if keep_val is None or merge_conf > keep_conf:
            setattr(keep, field, merge_val)
            keep.confidence[field] = merge_conf
            keep.source[field] = merge.source.get(field, "vlm")

    db.delete(merge)
    db.commit()
    db.refresh(keep)
    return keep
