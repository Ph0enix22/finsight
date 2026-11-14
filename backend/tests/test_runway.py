from fastapi.testclient import TestClient

from app.main import app


def _aarav_account_id(client: TestClient) -> int:
    return client.post("/api/demo/aarav").json()["account_id"]


def test_runway_matches_known_demo_facts() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        response = client.get("/api/runway", params={"account_id": account_id})
        assert response.status_code == 200
        body = response.json()

        assert body["as_of_date"] == "2026-11-14"
        assert body["current_balance_paise"] == 309600  # Rs 3,096 — pinned demo fact
        assert body["next_inflow_date"] == "2026-12-01"
        assert body["next_inflow_amount_paise"] == 900000  # Rs 9,000 allowance
        assert body["forecast"][0]["date"] == "2026-11-14"
        assert body["forecast"][-1]["date"] == "2026-12-01"
        assert 0.0 <= body["p_run_out"] <= 1.0
        assert body["safe_to_spend_per_day_paise"] >= 0
        assert len(body["txn_ids"]) > 0

        income_series = [s for s in body["recurring_series"] if s["direction"] == "CR"]
        assert len(income_series) == 1
        assert income_series[0]["typical_amount_paise"] == 900000
        assert income_series[0]["merchant_name"] == "Parent Allowance Credit"


def test_runway_forecast_percentiles_are_ordered() -> None:
    with TestClient(app) as client:
        account_id = _aarav_account_id(client)
        body = client.get("/api/runway", params={"account_id": account_id}).json()
        for point in body["forecast"]:
            assert point["p10"] <= point["median"] <= point["p90"]


def test_runway_unknown_account_404s() -> None:
    with TestClient(app) as client:
        response = client.get("/api/runway", params={"account_id": 999999999})
        assert response.status_code == 404


def test_runway_blank_account_falls_back_gracefully() -> None:
    with TestClient(app) as client:
        account_id = client.post("/api/accounts").json()["account_id"]
        response = client.get("/api/runway", params={"account_id": account_id})
        assert response.status_code == 200
        body = response.json()
        assert body["current_balance_paise"] == 0
        assert body["p_run_out"] == 0.0
        assert (
            len(body["forecast"]) == 31
        )  # 30-day fallback horizon, no income detected
