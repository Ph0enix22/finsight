from fastapi.testclient import TestClient

from app.main import app


def test_create_and_list_goal() -> None:
    with TestClient(app) as client:
        user_id = client.post("/api/accounts").json()["user_id"]
        created = client.post(
            "/api/goals",
            json={
                "user_id": user_id,
                "name": "MacBook",
                "target_amount_paise": 9_000_000,
                "target_date": "2027-03-01",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["saved_so_far_paise"] == 0

        listed = client.get("/api/goals", params={"user_id": user_id}).json()
        assert len(listed) == 1
        assert listed[0]["name"] == "MacBook"


def test_list_goals_scoped_to_user() -> None:
    with TestClient(app) as client:
        user_a = client.post("/api/accounts").json()["user_id"]
        user_b = client.post("/api/accounts").json()["user_id"]
        client.post(
            "/api/goals",
            json={
                "user_id": user_a,
                "name": "Goa trip",
                "target_amount_paise": 1_500_000,
                "target_date": "2027-01-01",
            },
        )
        assert client.get("/api/goals", params={"user_id": user_b}).json() == []
