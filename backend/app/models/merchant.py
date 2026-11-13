from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import Category


class Merchant(SQLModel, table=True):
    __tablename__ = "merchants"

    id: int | None = Field(default=None, primary_key=True)
    canonical_name: str
    vpa_patterns: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    default_category: Category
    logo_key: str | None = None
