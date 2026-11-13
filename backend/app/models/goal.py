from datetime import date

from sqlmodel import Field, SQLModel


class Goal(SQLModel, table=True):
    __tablename__ = "goals"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    name: str
    target_amount_paise: int
    target_date: date
    saved_so_far_paise: int = 0
