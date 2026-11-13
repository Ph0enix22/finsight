from datetime import date

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str | date]:
    return {"status": "ok", "as_of_date": settings.as_of_date}
