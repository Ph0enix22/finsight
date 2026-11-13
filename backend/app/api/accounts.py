from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.ingest import get_session
from app.models.account import Account
from app.models.user import User

router = APIRouter()


@router.post("/accounts")
def create_blank_account(session: Session = Depends(get_session)) -> dict:
    user = User(name="You", persona_key="custom")
    session.add(user)
    session.commit()
    session.refresh(user)

    account = Account(
        user_id=user.id,
        bank_label="Kaveri National Bank",
        masked_number="XX0000",
        current_balance_paise=0,
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    return {"user_id": user.id, "account_id": account.id}
