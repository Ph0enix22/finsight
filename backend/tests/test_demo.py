from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.db import engine
from app.main import app
from app.models.transaction import Transaction
from app.models.user import User


def test_load_demo_persona_creates_user_and_transactions() -> None:
    with TestClient(app) as client:
        response = client.post("/api/demo/aarav")
        assert response.status_code == 200
        body = response.json()
        assert body["persona_key"] == "aarav"
        assert isinstance(body["account_id"], int)

    with Session(engine) as session:
        user = session.exec(select(User).where(User.persona_key == "aarav")).first()
        assert user is not None
        txns = session.exec(select(Transaction)).all()
        assert len(txns) > 0


def test_load_demo_persona_is_idempotent() -> None:
    with TestClient(app) as client:
        client.post("/api/demo/aarav")
        client.post("/api/demo/aarav")

    with Session(engine) as session:
        users = session.exec(select(User).where(User.persona_key == "aarav")).all()
        assert len(users) == 1


def test_load_demo_persona_rejects_unknown_persona() -> None:
    with TestClient(app) as client:
        response = client.post("/api/demo/not-a-real-persona")
        assert response.status_code == 404
