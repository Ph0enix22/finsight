from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.util import utcnow


class Scenario(SQLModel, table=True):
    __tablename__ = "scenarios"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    events: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    result_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
