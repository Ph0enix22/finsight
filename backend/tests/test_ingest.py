from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import Category


def test_ingest_sms_creates_transaction() -> None:
    with TestClient(app) as client:
        sms = (
            "Dear Customer, Rs.249.00 debited from a/c XX4521 on 07-Nov-26 02:13 "
            "to VPA swiggy@ybl. Ref No 304857129384. Avl Bal Rs.3100.00. -KNB"
        )
        response = client.post(
            "/api/ingest/sms", json={"account_id": 1, "raw_text": sms}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["amount_paise"] == 24900
        assert body["direction"] == "DR"
        assert body["category"] == Category.FOOD_DELIVERY.value
        assert body["txn_ids"] == [body["txn_id"]]


def test_ingest_sms_rejects_unparseable_text() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/ingest/sms", json={"account_id": 1, "raw_text": "Your OTP is 123456"}
        )
        assert response.status_code == 422


def test_ingest_statement_csv() -> None:
    with TestClient(app) as client:
        csv_content = (
            "Date,Narration,Debit,Credit,Balance\n"
            "01/06/2026,UPI/DR/1234567890/swiggy@ybl/SWIGGY,249.00,,2851.00\n"
            "01/06/2026,UPI/CR/1234567891/employerpayroll@ybl/EMPLOYER PAYROLL,,68000.00,70851.00\n"
        )
        response = client.post(
            "/api/ingest/statement",
            params={"account_id": 1},
            files={"file": ("statement.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ingested"] == 2
        assert body["skipped"] == 0
