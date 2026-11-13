from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import AlertStatus, AlertType


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    type: AlertType
    txn_id: int = Field(foreign_key="transactions.id")
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: AlertStatus = AlertStatus.OPEN
