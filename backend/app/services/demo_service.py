import json
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from app.models.account import Account
from app.models.enums import Category, Direction, TxnSource
from app.models.transaction import Transaction
from app.models.user import User
from app.services.ingest_service import get_or_create_merchant

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "sample"

PERSONAS = {"aarav", "priya", "fatima"}


def load_persona(session: Session, persona: str) -> User:
    if persona not in PERSONAS:
        raise ValueError(
            f"unknown persona {persona!r}, expected one of {sorted(PERSONAS)}"
        )

    path = SAMPLE_DIR / f"{persona}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    # Idempotent: wipe any prior demo data for this persona before reseeding.
    existing_user = session.exec(
        select(User).where(User.persona_key == persona)
    ).first()
    if existing_user:
        accounts = session.exec(
            select(Account).where(Account.user_id == existing_user.id)
        ).all()
        for account in accounts:
            txns = session.exec(
                select(Transaction).where(Transaction.account_id == account.id)
            ).all()
            for t in txns:
                session.delete(t)
            session.delete(account)
        session.delete(existing_user)
        session.commit()

    user = User(name=persona.capitalize(), persona_key=persona)
    session.add(user)
    session.commit()
    session.refresh(user)

    account = Account(
        user_id=user.id,
        bank_label="Kaveri National Bank",
        masked_number="XX1234",
        current_balance_paise=payload["ending_balance_paise"],
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    for t in payload["txns"]:
        merchant = get_or_create_merchant(session, t["surface_name"], t["category"])
        txn = Transaction(
            account_id=account.id,
            ts=datetime.fromisoformat(t["ts"]).replace(tzinfo=UTC),
            amount_paise=t["amount_paise"],
            direction=Direction(t["direction"]),
            raw_text=t["surface_name"],
            source=TxnSource.SEED,
            merchant_id=merchant.id if merchant else None,
            category=Category(t["category"]),
            category_confidence=1.0,
            is_user_labelled=False,
            balance_after_paise=t["balance_after_paise"],
        )
        session.add(txn)
    session.commit()
    return user
