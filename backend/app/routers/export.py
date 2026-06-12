from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models import ItemRecord, User
from app.services import export as export_svc

router = APIRouter(prefix="/export", tags=["export"])


@router.get("")
def export_records(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    session_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    stmt = select(ItemRecord).where(ItemRecord.user_id == current_user.id)
    if session_id is not None:
        stmt = stmt.where(ItemRecord.session_id == session_id)
    records = list(db.scalars(stmt))

    if format == "xlsx":
        content = export_svc.to_xlsx(records)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "imdb_export.xlsx"
    else:
        content = export_svc.to_csv(records)
        media = "text/csv"
        filename = "imdb_export.csv"

    import io

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
