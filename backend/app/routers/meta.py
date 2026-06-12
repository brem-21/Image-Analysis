from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models import User
from app.schemas.imdb import WeightUnit
from app.services.normalize import CANONICAL

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/canonical")
def canonical_values(current_user: User = Depends(get_current_user)) -> dict[str, list[str]]:
    """Canonical dropdown values so the UI keeps naming centralized."""
    return {
        **{field: list(values) for field, values in CANONICAL.items()},
        "weight_unit": [u.value for u in WeightUnit],
    }
