from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.util import utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    persona_key: str
    created_at: datetime = Field(default_factory=utcnow)
