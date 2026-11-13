from fastapi.testclient import TestClient

from app.main import app


def test_create_blank_account() -> None:
    with TestClient(app) as client:
        response = client.post("/api/accounts")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["user_id"], int)
        assert isinstance(body["account_id"], int)


def test_blank_account_accepts_ingest() -> None:
    with TestClient(app) as client:
        account_id = client.post("/api/accounts").json()["account_id"]
        sms = (
            "Dear Customer, Rs.249.00 debited from a/c XX4521 on 07-Nov-26 02:13 "
            "to VPA swiggy@ybl. Ref No 304857129384. Avl Bal Rs.3100.00. -KNB"
        )
        response = client.post(
            "/api/ingest/sms", json={"account_id": account_id, "raw_text": sms}
        )
        assert response.status_code == 200
