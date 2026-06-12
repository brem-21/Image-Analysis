from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import ExtractionSession, ItemRecord, User
from app.schemas.imdb import SessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    """List the current user's scan batches (newest first) with item counts."""
    review_count = func.coalesce(
        func.sum(case((ItemRecord.needs_review.is_(True), 1), else_=0)), 0
    )
    stmt = (
        select(
            ExtractionSession.id,
            ExtractionSession.label,
            ExtractionSession.created_at,
            func.count(ItemRecord.id).label("item_count"),
            review_count.label("needs_review_count"),
        )
        .outerjoin(ItemRecord, ItemRecord.session_id == ExtractionSession.id)
        .where(ExtractionSession.user_id == current_user.id)
        .group_by(ExtractionSession.id)
        .order_by(ExtractionSession.created_at.desc(), ExtractionSession.id.desc())
    )
    return [
        SessionOut(
            id=row.id,
            label=row.label,
            created_at=row.created_at,
            item_count=row.item_count,
            needs_review_count=row.needs_review_count,
        )
        for row in db.execute(stmt).all()
    ]
