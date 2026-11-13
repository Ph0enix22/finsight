from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.ingest import get_session
from app.core.timezones import ist_day_end_utc, ist_day_start_utc
from app.models.enums import Category
from app.models.merchant import Merchant
from app.models.transaction import Transaction

router = APIRouter()


class TransactionOut(BaseModel):
    id: int
    ts: datetime
    amount_paise: int
    direction: str
    category: str | None
    category_confidence: float | None
    is_user_labelled: bool
    merchant_id: int | None
    merchant_name: str | None
    raw_text: str
    balance_after_paise: int | None


class RecategoriseRequest(BaseModel):
    category: Category


class RecategoriseResponse(BaseModel):
    updated_count: int
    txn_ids: list[int]


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    account_id: int,
    category: Category | None = None,
    merchant_id: int | None = None,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[TransactionOut]:
    stmt = select(Transaction).where(Transaction.account_id == account_id)
    if category is not None:
        stmt = stmt.where(Transaction.category == category)
    if merchant_id is not None:
        stmt = stmt.where(Transaction.merchant_id == merchant_id)
    if from_ is not None:
        stmt = stmt.where(Transaction.ts >= ist_day_start_utc(from_))
    if to is not None:
        stmt = stmt.where(Transaction.ts <= ist_day_end_utc(to))
    stmt = stmt.order_by(Transaction.ts.desc()).offset(offset).limit(limit)
    txns = session.exec(stmt).all()

    merchant_ids = {t.merchant_id for t in txns if t.merchant_id}
    merchants = {}
    if merchant_ids:
        rows = session.exec(select(Merchant).where(Merchant.id.in_(merchant_ids))).all()
        merchants = {m.id: m.canonical_name for m in rows}

    return [
        TransactionOut(
            id=t.id,
            ts=t.ts,
            amount_paise=t.amount_paise,
            direction=t.direction.value,
            category=t.category.value if t.category else None,
            category_confidence=t.category_confidence,
            is_user_labelled=t.is_user_labelled,
            merchant_id=t.merchant_id,
            merchant_name=merchants.get(t.merchant_id),
            raw_text=t.raw_text,
            balance_after_paise=t.balance_after_paise,
        )
        for t in txns
    ]


@router.patch("/transactions/{txn_id}", response_model=RecategoriseResponse)
def recategorise_transaction(
    txn_id: int, payload: RecategoriseRequest, session: Session = Depends(get_session)
) -> RecategoriseResponse:
    txn = session.get(Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="transaction not found")

    txn.category = payload.category
    txn.is_user_labelled = True
    session.add(txn)
    updated_ids = [txn.id]

    if txn.merchant_id is not None:
        similar = session.exec(
            select(Transaction).where(
                Transaction.merchant_id == txn.merchant_id,
                Transaction.is_user_labelled == False,
                Transaction.id != txn.id,
            )
        ).all()
        for other in similar:
            other.category = payload.category
            session.add(other)
            updated_ids.append(other.id)

    session.commit()
    return RecategoriseResponse(updated_count=len(updated_ids), txn_ids=updated_ids)
