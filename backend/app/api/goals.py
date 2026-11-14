from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.ingest import get_session
from app.models.goal import Goal

router = APIRouter()


class GoalCreate(BaseModel):
    user_id: int
    name: str
    target_amount_paise: int
    target_date: date
    saved_so_far_paise: int = 0


class GoalOut(BaseModel):
    id: int
    user_id: int
    name: str
    target_amount_paise: int
    target_date: date
    saved_so_far_paise: int


@router.post("/goals", response_model=GoalOut)
def create_goal(payload: GoalCreate, session: Session = Depends(get_session)) -> Goal:
    goal = Goal(**payload.model_dump())
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


@router.get("/goals", response_model=list[GoalOut])
def list_goals(user_id: int, session: Session = Depends(get_session)) -> list[Goal]:
    return list(session.exec(select(Goal).where(Goal.user_id == user_id)).all())
