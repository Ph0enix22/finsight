from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.ingest import get_session
from app.core.config import settings
from app.models.account import Account
from app.models.merchant import Merchant
from app.services.twin_service import (
    apply_recurring_changes,
    load_account_snapshot,
    persist_recurring_series,
    run_twin,
)
from finsight_ml.recurring import RecurringDetectionResult
from finsight_ml.twin import TwinResult, goal_reach_day

router = APIRouter()


class ForecastPointOut(BaseModel):
    date: date
    p10: int
    median: int
    p90: int


class ForecastOut(BaseModel):
    forecast: list[ForecastPointOut]
    p_run_out: float
    safe_to_spend_per_day_paise: int


def _forecast_out(result: TwinResult) -> ForecastOut:
    return ForecastOut(
        forecast=[
            ForecastPointOut(date=d, p10=p10, median=p50, p90=p90)
            for d, p10, p50, p90 in zip(
                result.dates, result.p10, result.p50, result.p90
            )
        ],
        p_run_out=result.p_run_out,
        safe_to_spend_per_day_paise=result.safe_to_spend_per_day_paise,
    )


class RecurringSeriesOut(BaseModel):
    merchant_id: int
    merchant_name: str | None
    direction: str
    period_days: int
    typical_amount_paise: int
    next_due: date


class RunwayResponse(ForecastOut):
    as_of_date: date
    current_balance_paise: int
    next_inflow_date: date
    next_inflow_amount_paise: int
    recurring_series: list[RecurringSeriesOut]
    txn_ids: list[int]


def _get_account_or_404(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account


def _recurring_series_out(
    session: Session, detection: RecurringDetectionResult
) -> list[RecurringSeriesOut]:
    merchant_ids = {item.merchant_id for item in detection.series}
    names: dict[int, str] = {}
    if merchant_ids:
        rows = session.exec(select(Merchant).where(Merchant.id.in_(merchant_ids))).all()
        names = {m.id: m.canonical_name for m in rows}
    return [
        RecurringSeriesOut(
            merchant_id=item.merchant_id,
            merchant_name=names.get(item.merchant_id),
            direction=item.direction,
            period_days=item.period_days,
            typical_amount_paise=item.typical_amount_paise,
            next_due=item.next_due,
        )
        for item in detection.series
    ]


@router.get("/runway", response_model=RunwayResponse)
def get_runway(
    account_id: int, session: Session = Depends(get_session)
) -> RunwayResponse:
    account = _get_account_or_404(session, account_id)
    as_of = settings.as_of_date
    snapshot = load_account_snapshot(session, account_id, as_of)
    persist_recurring_series(session, account.user_id, snapshot.detection)

    result = run_twin(snapshot)
    out = _forecast_out(result)
    return RunwayResponse(
        as_of_date=as_of,
        current_balance_paise=snapshot.current_balance_paise,
        next_inflow_date=snapshot.horizon_end(),
        next_inflow_amount_paise=snapshot.next_inflow_amount_paise(),
        recurring_series=_recurring_series_out(session, snapshot.detection),
        txn_ids=snapshot.all_txn_ids,
        **out.model_dump(),
    )


class TwinSimulateRequest(BaseModel):
    account_id: int
    events: list[dict[str, Any]] = []
    goal_target_amount_paise: int | None = None


class TwinSimulateResponse(BaseModel):
    as_of_date: date
    baseline: ForecastOut
    scenario: ForecastOut
    goal_delay_days: int | None
    txn_ids: list[int]


@router.post("/twin/simulate", response_model=TwinSimulateResponse)
def post_twin_simulate(
    payload: TwinSimulateRequest, session: Session = Depends(get_session)
) -> TwinSimulateResponse:
    _get_account_or_404(session, payload.account_id)
    as_of = settings.as_of_date
    snapshot = load_account_snapshot(session, payload.account_id, as_of)

    try:
        scenario_series, remaining_events = apply_recurring_changes(
            snapshot.detection.series, payload.events
        )
        baseline_result = run_twin(snapshot)
        scenario_result = run_twin(
            snapshot, events=tuple(remaining_events), series=scenario_series
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    goal_delay_days = None
    if payload.goal_target_amount_paise is not None:
        baseline_reach = goal_reach_day(
            baseline_result, payload.goal_target_amount_paise
        )
        scenario_reach = goal_reach_day(
            scenario_result, payload.goal_target_amount_paise
        )
        if baseline_reach is not None and scenario_reach is not None:
            goal_delay_days = (scenario_reach - baseline_reach).days

    return TwinSimulateResponse(
        as_of_date=as_of,
        baseline=_forecast_out(baseline_result),
        scenario=_forecast_out(scenario_result),
        goal_delay_days=goal_delay_days,
        txn_ids=snapshot.all_txn_ids,
    )
