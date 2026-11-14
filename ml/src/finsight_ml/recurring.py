"""Recurring-series + inflow-cadence detection: groups a user's transaction
history by merchant, checks interval regularity (weekly/monthly/yearly,
+-3 days), and reports amount stability + any price change on the latest
occurrence. Income/inflow cadence uses the same grouping on credits, but
falls back to a date/amount *range* (not a point estimate) when the gaps
don't cluster tightly enough to call it periodic — fatima's irregular
freelance credits are exactly this case, by design, not a detection failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

import numpy as np

CANONICAL_PERIODS_DAYS = (7, 30, 365)
PERIOD_TOLERANCE_DAYS = 3
PRICE_CHANGE_THRESHOLD = 0.10


@dataclass
class RecurringItem:
    merchant_id: int
    direction: str  # "DR" | "CR"
    period_days: int
    typical_amount_paise: int
    next_due: date
    last_amount_change_paise: int | None
    occurrences: int
    txn_ids: list[int] = field(default_factory=list)


@dataclass
class IrregularInflow:
    merchant_id: int
    next_inflow_date_low: date
    next_inflow_date_high: date
    amount_low_paise: int
    amount_high_paise: int
    occurrences: int
    txn_ids: list[int] = field(default_factory=list)


@dataclass
class RecurringDetectionResult:
    series: list[RecurringItem]
    irregular_inflows: list[IrregularInflow]

    def next_inflow(self) -> RecurringItem | IrregularInflow | None:
        """The single soonest-due credit — regular (next_due) or irregular
        (date-range low end) — used as the twin's default simulation horizon."""
        credits = [s for s in self.series if s.direction == "CR"]
        candidates: list[tuple[date, RecurringItem | IrregularInflow]] = [
            (s.next_due, s) for s in credits
        ] + [(i.next_inflow_date_low, i) for i in self.irregular_inflows]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c[0])[1]


def _parse_ts(ts: Any) -> datetime:
    return ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))


def _nearest_canonical_period(median_gap: float) -> int:
    return min(CANONICAL_PERIODS_DAYS, key=lambda p: abs(p - median_gap))


def _is_periodic(gaps: list[float], period: int) -> bool:
    return all(abs(gap - period) <= PERIOD_TOLERANCE_DAYS for gap in gaps)


def _advance_to_on_or_after(start: date, period_days: int, as_of: date) -> date:
    due = start
    while due < as_of:
        due += timedelta(days=period_days)
    return due


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, days_in_month(year, month))
    return date(year, month, day)


def days_in_month(year: int, month: int) -> int:
    next_month = date(year + (month == 12), (month % 12) + 1, 1)
    return (next_month - timedelta(days=1)).day


def _monthly_next_due(last_occurrence: date, as_of: date) -> date:
    """Calendar-month-aware next-due for a ~30-day series (e.g. "on the 1st")
    — advancing by a flat 30 days drifts off the actual day-of-month within a
    few cycles, which matters here since aarav's allowance and priya's salary
    are both real "same day every month" patterns, not every-30-days ones.
    `add_months` clamps to the target month's day count, so an anchor day
    like the 31st degrades gracefully (e.g. to the 28th) in short months."""
    months = 1
    due = add_months(last_occurrence, months)
    while due < as_of:
        months += 1
        due = add_months(last_occurrence, months)
    return due


def detect_recurring(
    transactions: list[dict[str, Any]], as_of: date
) -> RecurringDetectionResult:
    by_merchant: dict[int, list[dict[str, Any]]] = {}
    for t in transactions:
        merchant_id = t.get("merchant_id")
        if merchant_id is None:
            continue
        by_merchant.setdefault(merchant_id, []).append(t)

    series: list[RecurringItem] = []
    irregular_inflows: list[IrregularInflow] = []

    for merchant_id, txns in by_merchant.items():
        txns = sorted(txns, key=lambda t: _parse_ts(t["ts"]))
        if len(txns) < 2:
            continue
        direction = txns[-1]["direction"]
        same_direction = [t for t in txns if t["direction"] == direction]
        if len(same_direction) < 2:
            continue

        dates = [_parse_ts(t["ts"]).date() for t in same_direction]
        amounts = [int(t["amount_paise"]) for t in same_direction]
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        txn_ids = [t["id"] for t in same_direction if t.get("id") is not None]

        period = _nearest_canonical_period(median(gaps))
        if _is_periodic([float(g) for g in gaps], period):
            typical = int(median(amounts))
            latest = amounts[-1]
            change = latest - typical
            last_amount_change_paise = (
                change
                if abs(change) / max(typical, 1) > PRICE_CHANGE_THRESHOLD
                else None
            )
            next_due = (
                _monthly_next_due(dates[-1], as_of)
                if period == 30
                else _advance_to_on_or_after(
                    dates[-1] + timedelta(days=period), period, as_of
                )
            )
            series.append(
                RecurringItem(
                    merchant_id=merchant_id,
                    direction=direction,
                    period_days=period,
                    typical_amount_paise=typical,
                    next_due=next_due,
                    last_amount_change_paise=last_amount_change_paise,
                    occurrences=len(same_direction),
                    txn_ids=txn_ids,
                )
            )
        elif direction == "CR":
            # Doesn't cluster into a clean period — irregular inflow (fatima's
            # freelance case). Report a range instead of forcing a point guess.
            gap_arr = np.array(gaps, dtype=float)
            amount_arr = np.array(amounts, dtype=float)
            low_gap, high_gap = np.percentile(gap_arr, [10, 90])
            low_amt, high_amt = np.percentile(amount_arr, [10, 90])
            irregular_inflows.append(
                IrregularInflow(
                    merchant_id=merchant_id,
                    next_inflow_date_low=dates[-1] + timedelta(days=round(low_gap)),
                    next_inflow_date_high=dates[-1] + timedelta(days=round(high_gap)),
                    amount_low_paise=round(low_amt),
                    amount_high_paise=round(high_amt),
                    occurrences=len(same_direction),
                    txn_ids=txn_ids,
                )
            )

    return RecurringDetectionResult(series=series, irregular_inflows=irregular_inflows)


def variable_transactions(
    transactions: list[dict[str, Any]], result: RecurringDetectionResult
) -> list[dict[str, Any]]:
    """Transactions NOT explained by any detected recurring series or
    irregular inflow — the pool `finsight_ml.twin.simulate` should bootstrap
    from, so a known subscription/salary isn't sampled *and* injected."""
    explained_ids = {tid for item in result.series for tid in item.txn_ids}
    explained_ids |= {tid for item in result.irregular_inflows for tid in item.txn_ids}
    if not explained_ids:
        return transactions
    return [t for t in transactions if t.get("id") not in explained_ids]
