from fastapi.testclient import TestClient

from app.main import app


def _aarav_account_id(client: TestClient) -> int:
    return client.post("/api/demo/aarav").json()["account_id"]


def test_simulate_one_time_purchase_increases_run_out_risk() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.post(
            "/api/twin/simulate",
            json={
                "account_id": account_id,
                "events": [
                    {
                        "type": "one_time_purchase",
                        "amount_paise": 180000,
                        "date": "2026-11-14",
                    }
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["scenario"]["p_run_out"] >= body["baseline"]["p_run_out"]
        assert len(body["baseline"]["forecast"]) == len(body["scenario"]["forecast"])


def test_simulate_without_events_matches_baseline() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.post(
            "/api/twin/simulate", json={"account_id": account_id, "events": []}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["baseline"]["forecast"] == body["scenario"]["forecast"]
        assert body["baseline"]["p_run_out"] == body["scenario"]["p_run_out"]
        assert body["goal_delay_days"] is None


def test_simulate_goal_delay_days_reported_when_target_given() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.post(
            "/api/twin/simulate",
            json={
                "account_id": account_id,
                "events": [
                    {
                        "type": "one_time_purchase",
                        "amount_paise": 50000,
                        "date": "2026-11-14",
                    }
                ],
                "goal_target_amount_paise": 850000,
            },
        )
        assert response.status_code == 200
        body = response.json()
        # spending more today can only delay (or leave unchanged) reaching a
        # savings target later, never pull it earlier
        assert body["goal_delay_days"] is None or body["goal_delay_days"] >= 0


def test_simulate_recurring_change_cancel_unknown_merchant_is_a_no_op() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.post(
            "/api/twin/simulate",
            json={
                "account_id": account_id,
                "events": [
                    {
                        "type": "recurring_change",
                        "mode": "cancel",
                        "merchant_id": 999999,
                    }
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["baseline"]["forecast"] == body["scenario"]["forecast"]


def test_simulate_recurring_change_add_bill_increases_run_out_risk() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.post(
            "/api/twin/simulate",
            json={
                "account_id": account_id,
                "events": [
                    {
                        "type": "recurring_change",
                        "mode": "add",
                        "direction": "DR",
                        "period_days": 30,
                        "typical_amount_paise": 500000,
                        "next_due": "2026-11-20",
                    }
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["scenario"]["p_run_out"] >= body["baseline"]["p_run_out"]
        assert (
            body["scenario"]["forecast"][-1]["median"]
            <= body["baseline"]["forecast"][-1]["median"]
        )


def test_simulate_unknown_event_type_422s() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.post(
            "/api/twin/simulate",
            json={"account_id": account_id, "events": [{"type": "not_a_real_event"}]},
        )
        assert response.status_code == 422


def test_simulate_unknown_account_404s() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/twin/simulate", json={"account_id": 999999999, "events": []}
        )
        assert response.status_code == 404
