from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.db import engine
from app.main import app
from app.models.account import Account
from app.models.user import User


def _aarav_account_id(client: TestClient) -> int:
    client.post("/api/demo/aarav")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.persona_key == "aarav")).first()
        account = session.exec(
            select(Account).where(Account.user_id == user.id)
        ).first()
        return account.id


def test_list_transactions_filters_by_category() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.get(
            "/api/transactions",
            params={
                "account_id": account_id,
                "category": "food_delivery",
                "limit": 500,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) > 0
        assert all(t["category"] == "food_delivery" for t in body)


def test_recategorise_relabels_same_merchant() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        txns = client.get(
            "/api/transactions",
            params={
                "account_id": account_id,
                "category": "food_delivery",
                "limit": 500,
            },
        ).json()
        same_merchant = [t for t in txns if t["merchant_id"] == txns[0]["merchant_id"]]
        assert (
            len(same_merchant) > 1
        ), "fixture should have >1 txn for the same merchant to test bulk relabel"

        response = client.patch(
            f"/api/transactions/{txns[0]['id']}", json={"category": "entertainment"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["updated_count"] == len(same_merchant)

        refreshed = client.get(
            "/api/transactions",
            params={
                "account_id": account_id,
                "category": "entertainment",
                "limit": 500,
            },
        ).json()
        refreshed_ids = {t["id"] for t in refreshed}
        assert {t["id"] for t in same_merchant} <= refreshed_ids


def test_recategorise_unknown_txn_404s() -> None:
    with TestClient(app) as client:
        response = client.patch(
            "/api/transactions/999999999", json={"category": "shopping"}
        )
        assert response.status_code == 404


def test_transactions_to_filter_uses_ist_calendar_day_not_utc() -> None:
    # 00:15 IST on 15-Nov is 18:45 UTC on 14-Nov. A naive UTC-midnight
    # boundary for `to=2026-11-14` would wrongly include it; the real IST
    # calendar-day boundary must exclude it.
    with TestClient(app) as client:
        account_id = client.post("/api/accounts").json()["account_id"]
        sms = (
            "SDB: INR 50.00 paid to midnighttest@ybl UPI Ref SDB1 on 15-Nov-26 "
            "00:15. Available balance INR 1,000.00"
        )
        txn_id = client.post(
            "/api/ingest/sms", json={"account_id": account_id, "raw_text": sms}
        ).json()["txn_id"]

        same_day = client.get(
            "/api/transactions",
            params={"account_id": account_id, "to": "2026-11-14", "limit": 10},
        ).json()
        assert txn_id not in {t["id"] for t in same_day}

        next_day = client.get(
            "/api/transactions",
            params={"account_id": account_id, "to": "2026-11-15", "limit": 10},
        ).json()
        assert txn_id in {t["id"] for t in next_day}
