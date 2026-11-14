"""Monte Carlo balance simulator: known recurring flows (from
`finsight_ml.recurring`) are injected into every path deterministically;
non-recurring day-to-day spend is bootstrapped from the last ~90 days,
conditioned on category and, when an income cycle is detected, which third
of the pay cycle a day falls in (falls back to plain weekday x category
otherwise). The phase conditioning matters in practice, not just in theory:
backtesting against aarav's real history showed spend tapering off sharply
in the back half of a pay cycle (people spend less as cash gets tight) —
weekday x category alone mixes "flush early-cycle" and "tight late-cycle"
days together and systematically overstates late-cycle run-out risk.
`events` (the "what if" layer) are injected the same deterministic way
recurring flows are — they represent a hypothesis, not uncertainty, so
every path sees them identically.

Day 0 of the simulation is `as_of` itself (not day 1) — that's what lets a
"what if I buy this today" event apply without a separate balance-adjustment
special case: day 0 gets no bootstrap draw (today's actual spend is already
baked into `current_balance_paise`), but it *does* get same-day deterministic
injections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from finsight_ml.recurring import RecurringItem, add_months

RUN_OUT_TARGET = 0.20
BOOTSTRAP_WINDOW_DAYS = 90


@dataclass
class TwinResult:
    dates: list[date]
    p10: list[int]
    p50: list[int]
    p90: list[int]
    p_run_out: float
    safe_to_spend_per_day_paise: int
    balances: (
        np.ndarray
    )  # (n_days+1, n_paths) — internal use (goal_reach_day, backtest)


def _parse_ts(ts: Any) -> datetime:
    return ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))


def _next_due_after(current_due: date, period_days: int) -> date:
    return (
        add_months(current_due, 1)
        if period_days == 30
        else current_due + timedelta(days=period_days)
    )


def _prev_due_before(current_due: date, period_days: int) -> date:
    return (
        add_months(current_due, -1)
        if period_days == 30
        else current_due - timedelta(days=period_days)
    )


def _payday_dates(
    recurring: list[RecurringItem], range_start: date, range_end: date
) -> list[date]:
    """Every actual/implied income date (any detected CR series) spanning
    the bootstrap window through the simulation horizon, used to phase-bucket
    days within their enclosing pay cycle. Only on the income side — bills
    cycle too, but it's the income gap that drives tapering behaviour."""
    paydays: set[date] = set()
    for item in recurring:
        if item.direction != "CR":
            continue
        d = item.next_due
        while d >= range_start:
            paydays.add(d)
            d = _prev_due_before(d, item.period_days)
        d = item.next_due
        # one extra step past range_end so a day exactly ON range_end (e.g.
        # horizon_end itself) still has a strictly-later payday to bracket
        # against, instead of falling back to the (disjoint) weekday key.
        while d <= range_end:
            paydays.add(d)
            d = _next_due_after(d, item.period_days)
        paydays.add(d)
    return sorted(paydays)


def _cycle_phase(d: date, paydays: list[date]) -> int | None:
    """Which third of its pay cycle `d` falls in (0=early, 2=late), or None
    if `d` can't be bracketed by two known paydays (no income detected, or
    `d` falls outside the known payday range)."""
    prior = max((p for p in paydays if p <= d), default=None)
    nxt = min((p for p in paydays if p > d), default=None)
    if prior is None or nxt is None or nxt <= prior:
        return None
    return min(2, int((d - prior).days / (nxt - prior).days * 3))


def _build_pools(
    variable_pool: list[dict[str, Any]],
    window_start: date,
    window_end: date,
    paydays: list[date],
) -> tuple[dict[Any, dict[str, np.ndarray]], bool]:
    """Pools keyed by cycle-phase tercile when >=2 paydays bracket the
    window (the common, income-detected case); falls back to plain weekday
    otherwise — e.g. a brand-new account with no income history yet."""
    daily_totals: dict[date, dict[str, int]] = {}
    for t in variable_pool:
        if t["direction"] != "DR":
            continue
        d = _parse_ts(t["ts"]).date()
        if not (window_start <= d <= window_end):
            continue
        category = t.get("category") or "uncategorised"
        bucket = daily_totals.setdefault(d, {})
        bucket[category] = bucket.get(category, 0) + int(t["amount_paise"])

    categories = sorted({c for day in daily_totals.values() for c in day})
    use_phase = len(paydays) >= 2
    raw: dict[Any, dict[str, list[int]]] = {}

    d = window_start
    while d <= window_end:
        key = _pool_key(d, paydays, use_phase)
        bucket = raw.setdefault(key, {c: [] for c in categories})
        day_totals = daily_totals.get(d, {})
        for c in categories:
            bucket[c].append(day_totals.get(c, 0))
        d += timedelta(days=1)

    pools = {
        key: {c: np.array(v, dtype=float) for c, v in cats.items()}
        for key, cats in raw.items()
    }
    return pools, use_phase


def _pool_key(d: date, paydays: list[date], use_phase: bool) -> tuple[str, int]:
    phase = _cycle_phase(d, paydays) if use_phase else None
    # Tagged so a weekday fallback (e.g. a day outside the known payday
    # range) can never collide with a same-numbered phase bucket — both are
    # small ints (phase: 0-2, weekday: 0-6) and did collide before tagging.
    return ("wd", d.weekday()) if phase is None else ("phase", phase)


def _inject_recurring(
    deltas: np.ndarray, item: RecurringItem, as_of: date, n_days: int
) -> None:
    sign = 1 if item.direction == "CR" else -1
    due = item.next_due
    while (idx := (due - as_of).days) <= n_days:
        if idx >= 0:
            deltas[idx] += sign * item.typical_amount_paise
        due = _next_due_after(due, item.period_days)


def _inject_event(
    deltas: np.ndarray, event: dict[str, Any], as_of: date, n_days: int
) -> None:
    etype = event["type"]

    def _apply(d: date, amount_paise: int) -> None:
        idx = (d - as_of).days
        if 0 <= idx <= n_days:
            deltas[idx] -= amount_paise

    if etype == "one_time_purchase":
        _apply(date.fromisoformat(event["date"]), int(event["amount_paise"]))
    elif etype == "emi":
        due = date.fromisoformat(event["start_date"])
        for _ in range(int(event["months"])):
            _apply(due, int(event["amount_paise"]))
            due = add_months(due, 1)
    elif etype == "trip":
        start = date.fromisoformat(event["start_date"])
        end = date.fromisoformat(event["end_date"])
        trip_days = [
            start + timedelta(days=i) for i in range((end - start).days + 1)
        ] or [start]
        amount = int(event["amount_paise"])
        per_day, remainder = divmod(amount, len(trip_days))
        for i, d in enumerate(trip_days):
            _apply(d, per_day + (remainder if i == len(trip_days) - 1 else 0))
    elif etype == "goal":
        pass  # no balance effect — tracked via goal_reach_day against the result
    else:
        raise ValueError(f"unknown event type: {etype!r}")


def _walk_with_floor(current_balance_paise: int, daily_delta: np.ndarray) -> np.ndarray:
    """Day-by-day balance walk, vectorised over paths, with a floor at zero:
    a debit that would overdraw only drains down to zero. See the comment at
    simulate()'s call site for why this differs from a plain cumsum."""
    n_rows, n_paths = daily_delta.shape
    balance = np.full(n_paths, float(current_balance_paise))
    out = np.empty((n_rows, n_paths))
    for i in range(n_rows):
        balance = balance + np.maximum(daily_delta[i], -balance)
        out[i] = balance
    return out


def simulate(
    variable_pool: list[dict[str, Any]],
    recurring: list[RecurringItem],
    current_balance_paise: int,
    as_of: date,
    horizon_end: date,
    events: tuple[dict[str, Any], ...] = (),
    n_paths: int = 1000,
    seed: int | None = None,
) -> TwinResult:
    n_days = (horizon_end - as_of).days
    if n_days < 0:
        raise ValueError("horizon_end must be on or after as_of")

    window_end = as_of - timedelta(days=1)
    window_start = window_end - timedelta(days=BOOTSTRAP_WINDOW_DAYS - 1)
    paydays = _payday_dates(recurring, window_start, horizon_end)
    pools, use_phase = _build_pools(variable_pool, window_start, window_end, paydays)

    rng = np.random.default_rng(seed)
    dates = [as_of + timedelta(days=i) for i in range(n_days + 1)]

    variable_matrix = np.zeros((n_days + 1, n_paths))
    for i, d in enumerate(dates):
        if i == 0:
            continue  # today's actual spend is already in current_balance_paise
        key = _pool_key(d, paydays, use_phase)
        for pool in pools.get(key, {}).values():
            if pool.size:
                variable_matrix[i] += rng.choice(pool, size=n_paths, replace=True)

    deterministic = np.zeros(n_days + 1)
    for item in recurring:
        _inject_recurring(deterministic, item, as_of, n_days)
    for event in events:
        _inject_event(deterministic, event, as_of, n_days)

    daily_delta = -variable_matrix + deterministic[:, None]
    # Two balance walks, on purpose: a plain cumsum lets a path dip
    # arbitrarily negative mid-walk and "recover" later, which both
    # understates every later day's true available balance (money that
    # would've stayed unspent on a declined transaction keeps compounding
    # away) and overstates P(run out) by counting excursions that would
    # never really happen — real accounts can't go negative (declined
    # overdraws), matching generate.py's own invariant. The floored walk is
    # what gets reported as the forecast (p10/p50/p90); the unclipped shadow
    # walk is what P(run out) is measured against, since "would have
    # overdrawn" is exactly the risk signal that metric exists to carry.
    shadow_balance_paths = current_balance_paise + np.cumsum(daily_delta, axis=0)
    balance_paths = _walk_with_floor(current_balance_paise, daily_delta)

    p10 = np.percentile(balance_paths, 10, axis=1)
    p50 = np.percentile(balance_paths, 50, axis=1)
    p90 = np.percentile(balance_paths, 90, axis=1)
    p_run_out = float(np.mean(np.any(shadow_balance_paths < 0, axis=0)))

    safe_to_spend = _solve_safe_to_spend(
        current_balance_paise, variable_matrix, deterministic
    )

    return TwinResult(
        dates=dates,
        p10=[round(v) for v in p10],
        p50=[round(v) for v in p50],
        p90=[round(v) for v in p90],
        p_run_out=p_run_out,
        safe_to_spend_per_day_paise=safe_to_spend,
        balances=balance_paths,
    )


def _solve_safe_to_spend(
    current_balance_paise: int,
    variable_matrix: np.ndarray,
    deterministic: np.ndarray,
    target: float = RUN_OUT_TARGET,
) -> int:
    """Largest constant extra daily spend such that P(run out) stays <= target,
    found by bisection — p_run_out is monotonic non-decreasing in the extra
    drain, so this always converges to the threshold crossing."""
    n_days = variable_matrix.shape[0] - 1  # day 0 never carries a discretionary drain

    def p_run_out_for(extra_per_day: float) -> float:
        extra = np.zeros(variable_matrix.shape[0])
        extra[1:] = extra_per_day
        daily_delta = -variable_matrix + (deterministic - extra)[:, None]
        balance_paths = current_balance_paise + np.cumsum(daily_delta, axis=0)
        return float(np.mean(np.any(balance_paths < 0, axis=0)))

    if n_days <= 0 or p_run_out_for(0.0) > target:
        return 0

    lo, hi = 0.0, max(current_balance_paise / max(n_days, 1), 1.0)
    while p_run_out_for(hi) <= target and hi < current_balance_paise:
        hi *= 2
    for _ in range(30):
        mid = (lo + hi) / 2
        if p_run_out_for(mid) <= target:
            lo = mid
        else:
            hi = mid
    return int(lo)


def goal_reach_day(result: TwinResult, target_amount_paise: int) -> date | None:
    """First date the median path's balance reaches `target_amount_paise`, or
    None if it never does within the simulated horizon."""
    median = np.array(result.p50)
    reached = np.flatnonzero(median >= target_amount_paise)
    return result.dates[int(reached[0])] if reached.size else None
