import time
from datetime import date, timedelta

import numpy as np

from finsight_ml.recurring import RecurringItem
from finsight_ml.twin import goal_reach_day, simulate

AS_OF = date(2026, 11, 14)


def test_no_variable_spend_no_events_is_flat() -> None:
    result = simulate(
        [],
        [],
        current_balance_paise=100_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=5),
    )
    assert result.p10 == result.p50 == result.p90 == [100_000] * 6
    assert result.p_run_out == 0.0


def test_recurring_credit_injected_on_due_date() -> None:
    recurring = [
        RecurringItem(
            merchant_id=1,
            direction="CR",
            period_days=30,
            typical_amount_paise=900_000,
            next_due=AS_OF + timedelta(days=3),
            last_amount_change_paise=None,
            occurrences=5,
        )
    ]
    result = simulate(
        [],
        recurring,
        current_balance_paise=10_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=5),
    )
    assert result.p50[2] == 10_000  # day before the credit, unchanged
    assert result.p50[3] == 910_000  # credit lands exactly on day 3


def test_one_time_purchase_today_applies_immediately() -> None:
    result = simulate(
        [],
        [],
        current_balance_paise=50_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=2),
        events=(
            {
                "type": "one_time_purchase",
                "amount_paise": 20_000,
                "date": AS_OF.isoformat(),
            },
        ),
    )
    assert result.p50[0] == 30_000
    assert result.p50[1] == 30_000
    assert result.p50[2] == 30_000


def test_emi_deducts_each_month_within_horizon() -> None:
    result = simulate(
        [],
        [],
        current_balance_paise=500_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=65),
        events=(
            {
                "type": "emi",
                "amount_paise": 10_000,
                "months": 3,
                "start_date": AS_OF.isoformat(),
            },
        ),
    )
    # 3 emi payments of 10_000 each land within a 65-day horizon (roughly monthly)
    assert result.p50[-1] == 500_000 - 3 * 10_000


def test_trip_cost_spreads_across_days_and_sums_exactly() -> None:
    start = AS_OF + timedelta(days=1)
    end = AS_OF + timedelta(days=4)
    result = simulate(
        [],
        [],
        current_balance_paise=100_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=10),
        events=(
            {
                "type": "trip",
                "amount_paise": 10_000,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        ),
    )
    assert result.p50[-1] == 90_000  # full trip cost deducted by the end
    assert result.p50[0] == 100_000  # nothing deducted before the trip starts


def test_bootstrap_variable_spend_produces_ordered_percentiles() -> None:
    variable_pool = []
    day = AS_OF - timedelta(days=90)
    while day < AS_OF:
        variable_pool.append(
            {
                "ts": f"{day.isoformat()}T12:00:00",
                "amount_paise": 100 + (day.day % 7) * 50,
                "direction": "DR",
                "category": "food_delivery",
            }
        )
        day += timedelta(days=1)

    result = simulate(
        variable_pool,
        [],
        current_balance_paise=200_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=14),
        seed=42,
    )
    for p10, p50, p90 in zip(result.p10, result.p50, result.p90):
        assert p10 <= p50 <= p90


def test_seed_is_reproducible() -> None:
    variable_pool = [
        {
            "ts": f"2026-09-{d:02d}T12:00:00",
            "amount_paise": 500,
            "direction": "DR",
            "category": "food_delivery",
        }
        for d in range(1, 29)
    ]
    kwargs = {
        "variable_pool": variable_pool,
        "recurring": [],
        "current_balance_paise": 50_000,
        "as_of": AS_OF,
        "horizon_end": AS_OF + timedelta(days=10),
        "seed": 7,
    }
    r1 = simulate(**kwargs)
    r2 = simulate(**kwargs)
    assert r1.p50 == r2.p50
    assert r1.p10 == r2.p10


def test_certain_run_out_when_drain_exceeds_balance() -> None:
    recurring = [
        RecurringItem(
            merchant_id=2,
            direction="DR",
            period_days=7,
            typical_amount_paise=100_000,
            next_due=AS_OF + timedelta(days=1),
            last_amount_change_paise=None,
            occurrences=3,
        )
    ]
    result = simulate(
        [],
        recurring,
        current_balance_paise=50_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=3),
    )
    assert result.p_run_out == 1.0


def test_safe_to_spend_matches_even_split_when_deterministic() -> None:
    n_days = 10
    result = simulate(
        [],
        [],
        current_balance_paise=100_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=n_days),
    )
    assert abs(result.safe_to_spend_per_day_paise - 100_000 // n_days) <= 2


def test_safe_to_spend_is_zero_when_already_underwater() -> None:
    recurring = [
        RecurringItem(
            merchant_id=3,
            direction="DR",
            period_days=7,
            typical_amount_paise=200_000,
            next_due=AS_OF,
            last_amount_change_paise=None,
            occurrences=3,
        )
    ]
    result = simulate(
        [],
        recurring,
        current_balance_paise=50_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=5),
    )
    assert result.safe_to_spend_per_day_paise == 0


def test_goal_reach_day_finds_first_crossing_and_none_otherwise() -> None:
    recurring = [
        RecurringItem(
            merchant_id=4,
            direction="CR",
            period_days=30,
            typical_amount_paise=50_000,
            next_due=AS_OF + timedelta(days=2),
            last_amount_change_paise=None,
            occurrences=5,
        )
    ]
    result = simulate(
        [],
        recurring,
        current_balance_paise=0,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=5),
    )
    assert goal_reach_day(result, 50_000) == AS_OF + timedelta(days=2)
    assert goal_reach_day(result, 1_000_000) is None


def test_runs_fast_enough_for_1000_paths_over_a_month() -> None:
    variable_pool = [
        {
            "ts": f"2026-09-{d:02d}T12:00:00",
            "amount_paise": 300,
            "direction": "DR",
            "category": "food_delivery",
        }
        for d in range(1, 29)
    ]
    start = time.perf_counter()
    simulate(
        variable_pool,
        [],
        current_balance_paise=300_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=30),
        n_paths=1000,
        seed=1,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 300, f"simulate() took {elapsed_ms:.1f}ms, budget is 300ms"


def test_reported_balance_never_negative_even_when_shadow_run_out_risk_is() -> None:
    # A big debit today that exceeds current balance: the REPORTED trajectory
    # must floor at 0 (a real account can't go negative — declined overdraw),
    # but p_run_out must still flag the risk using the unclipped shadow walk.
    result = simulate(
        [],
        [],
        current_balance_paise=10_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=3),
        events=(
            {
                "type": "one_time_purchase",
                "amount_paise": 50_000,
                "date": AS_OF.isoformat(),
            },
        ),
    )
    assert min(result.p10 + result.p50 + result.p90) >= 0
    assert result.p50[0] == 0
    assert result.p_run_out == 1.0


def test_recovering_after_a_dip_is_not_double_counted_against_later_days() -> None:
    # Day 0: a purchase that would overdraw by 5_000. Day 1: a 20_000 credit.
    # The floored walk should land on exactly 20_000 — the overdrawn amount
    # is capped at day 0, not carried forward as a deeper debt that day 1's
    # credit has to climb out of first.
    recurring = [
        RecurringItem(
            merchant_id=5,
            direction="CR",
            period_days=30,
            typical_amount_paise=20_000,
            next_due=AS_OF + timedelta(days=1),
            last_amount_change_paise=None,
            occurrences=5,
        )
    ]
    result = simulate(
        [],
        recurring,
        current_balance_paise=10_000,
        as_of=AS_OF,
        horizon_end=AS_OF + timedelta(days=1),
        events=(
            {
                "type": "one_time_purchase",
                "amount_paise": 15_000,
                "date": AS_OF.isoformat(),
            },
        ),
    )
    assert result.p50[0] == 0  # 10_000 - 15_000 floored at 0, not -5_000
    assert result.p50[1] == 20_000  # 0 + 20_000, not -5_000 + 20_000 = 15_000


def test_percentile_arrays_use_numpy_without_crashing_on_empty_recurring() -> None:
    result = simulate([], [], current_balance_paise=1, as_of=AS_OF, horizon_end=AS_OF)
    assert result.dates == [AS_OF]
    assert isinstance(result.balances, np.ndarray)
