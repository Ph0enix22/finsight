from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.enums import Category, Direction, TxnSource


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id")
    ts: datetime
    amount_paise: int
    direction: Direction
    raw_text: str
    source: TxnSource
    merchant_id: int | None = Field(default=None, foreign_key="merchants.id")
    category: Category | None = None
    category_confidence: float | None = None
    is_user_labelled: bool = False
    recurring_id: int | None = Field(default=None, foreign_key="recurring_series.id")
    anomaly_score: float | None = None
    balance_after_paise: int | None = None
