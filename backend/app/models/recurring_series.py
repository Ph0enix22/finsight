from datetime import date

from sqlmodel import Field, SQLModel


class RecurringSeries(SQLModel, table=True):
    __tablename__ = "recurring_series"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    merchant_id: int = Field(foreign_key="merchants.id")
    period_days: int
    typical_amount_paise: int
    next_due: date
    last_amount_change_paise: int | None = None
