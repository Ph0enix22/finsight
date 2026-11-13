from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.ingest import get_session
from app.services.demo_service import PERSONAS, load_persona

router = APIRouter()


@router.post("/demo/{persona}")
def load_demo_persona(persona: str, session: Session = Depends(get_session)) -> dict:
    if persona not in PERSONAS:
        raise HTTPException(status_code=404, detail=f"unknown persona {persona!r}")
    user = load_persona(session, persona)
    return {"user_id": user.id, "persona_key": user.persona_key}
