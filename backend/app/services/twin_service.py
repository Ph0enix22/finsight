"""Bridges real account data to finsight_ml's recurring/twin modules. Used by
both GET /runway (baseline only) and POST /twin/simulate (baseline vs
scenario), so the "what a user's real history looks like to the model" logic
lives in exactly one place.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, delete, select

from app.core.timezones import ist_day_end_utc
from app.models.account import Account
from app.models.recurring_series import RecurringSeries
from app.models.transaction import Transaction
from finsight_ml.recurring import (
    IrregularInflow,
    RecurringDetectionResult,
    RecurringItem,
    detect_recurring,
    variable_transactions,
)
from finsight_ml.twin import TwinResult, simulate

FALLBACK_HORIZON_DAYS = 30  # no income history yet (e.g. a brand-new account)
N_PATHS = 1000
SIMULATION_SEED = 42  # deterministic responses — same inputs, same forecast


def _txn_to_dict(t: Transaction) -> dict[str, Any]:
    return {
        "id": t.id,
        "ts": t.ts.isoformat(),
        "amount_paise": t.amount_paise,
        "direction": t.direction.value,
        "category": t.category.value if t.category else None,
        "merchant_id": t.merchant_id,
    }


class AccountSnapshot:
    def __init__(
        self,
        as_of: date,
        current_balance_paise: int,
        detection: RecurringDetectionResult,
        variable_pool: list[dict[str, Any]],
        all_txn_ids: list[int],
    ) -> None:
        self.as_of = as_of
        self.current_balance_paise = current_balance_paise
        self.detection = detection
        self.variable_pool = variable_pool
        self.all_txn_ids = all_txn_ids

    def horizon_end(self) -> date:
        inflow = self.detection.next_inflow()
        if inflow is None:
            return self.as_of + timedelta(days=FALLBACK_HORIZON_DAYS)
        due = (
            inflow.next_due
            if isinstance(inflow, RecurringItem)
            else inflow.next_inflow_date_low
        )
        return max(due, self.as_of + timedelta(days=1))

    def next_inflow_amount_paise(self) -> int:
        inflow = self.detection.next_inflow()
        if inflow is None:
            return 0
        if isinstance(inflow, RecurringItem):
            return inflow.typical_amount_paise
        assert isinstance(inflow, IrregularInflow)
        return (inflow.amount_low_paise + inflow.amount_high_paise) // 2


def load_account_snapshot(
    session: Session, account_id: int, as_of: date
) -> AccountSnapshot:
    stmt = (
        select(Transaction)
        .where(Transaction.account_id == account_id)
        .where(Transaction.ts <= ist_day_end_utc(as_of))
        .order_by(Transaction.ts)
    )
    txns = session.exec(stmt).all()
    txn_dicts = [_txn_to_dict(t) for t in txns]

    detection = detect_recurring(txn_dicts, as_of)
    variable_pool = variable_transactions(txn_dicts, detection)

    balance = None
    for t in reversed(txns):
        if t.balance_after_paise is not None:
            balance = t.balance_after_paise
            break
    if balance is None:
        account = session.get(Account, account_id)
        balance = account.current_balance_paise if account else 0

    return AccountSnapshot(
        as_of=as_of,
        current_balance_paise=balance,
        detection=detection,
        variable_pool=variable_pool,
        all_txn_ids=[t["id"] for t in txn_dicts],
    )


def persist_recurring_series(
    session: Session, user_id: int, detection: RecurringDetectionResult
) -> None:
    """Best-effort cache of the detected series in the DB table SPEC calls
    for — requests don't depend on this being fresh (they always recompute
    live from transactions), so a failed/partial write here never breaks
    /runway or /twin/simulate."""
    session.exec(delete(RecurringSeries).where(RecurringSeries.user_id == user_id))
    for item in detection.series:
        session.add(
            RecurringSeries(
                user_id=user_id,
                merchant_id=item.merchant_id,
                period_days=item.period_days,
                typical_amount_paise=item.typical_amount_paise,
                next_due=item.next_due,
                last_amount_change_paise=item.last_amount_change_paise,
            )
        )
    session.commit()


def run_twin(
    snapshot: AccountSnapshot,
    events: tuple[dict[str, Any], ...] = (),
    series: list[RecurringItem] | None = None,
) -> TwinResult:
    return simulate(
        snapshot.variable_pool,
        snapshot.detection.series if series is None else series,
        snapshot.current_balance_paise,
        snapshot.as_of,
        snapshot.horizon_end(),
        events=events,
        n_paths=N_PATHS,
        seed=SIMULATION_SEED,
    )


def apply_recurring_changes(
    series: list[RecurringItem], events: list[dict[str, Any]]
) -> tuple[list[RecurringItem], list[dict[str, Any]]]:
    """`recurring_change` (cancel/add a subscription or bill) isn't a
    finsight_ml.twin event type — unlike a one-off purchase/EMI/trip, it
    changes what's injected on EVERY future occurrence, not a fixed date, so
    it's simplest to apply by editing the recurring-series list itself before
    simulating, rather than teaching twin.py a third injection mechanism.
    Returns the modified series plus whatever events are left for simulate()
    to handle normally."""
    modified = list(series)
    remaining: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "recurring_change":
            remaining.append(event)
            continue
        mode = event.get("mode")
        if mode == "cancel":
            merchant_id = event["merchant_id"]
            modified = [s for s in modified if s.merchant_id != merchant_id]
        elif mode == "add":
            modified.append(
                RecurringItem(
                    merchant_id=event.get("merchant_id", -1),
                    direction=event.get("direction", "DR"),
                    period_days=int(event["period_days"]),
                    typical_amount_paise=int(event["typical_amount_paise"]),
                    next_due=date.fromisoformat(event["next_due"]),
                    last_amount_change_paise=None,
                    occurrences=1,
                )
            )
        else:
            raise ValueError(f"unknown recurring_change mode: {mode!r}")
    return modified, remaining
