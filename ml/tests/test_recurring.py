from datetime import date

from finsight_ml.recurring import detect_recurring, variable_transactions


def _txn(
    ts: str,
    amount_paise: int,
    direction: str,
    merchant_id: int,
    txn_id: int | None = None,
) -> dict:
    return {
        "id": txn_id,
        "ts": ts,
        "amount_paise": amount_paise,
        "direction": direction,
        "merchant_id": merchant_id,
    }


def test_weekly_subscription_detected() -> None:
    txns = [
        _txn(f"2026-10-{d:02d}T10:00:00", 11900, "DR", 1) for d in (1, 8, 15, 22, 29)
    ]
    result = detect_recurring(txns, as_of=date(2026, 11, 1))
    assert len(result.series) == 1
    item = result.series[0]
    assert item.period_days == 7
    assert item.typical_amount_paise == 11900
    assert item.last_amount_change_paise is None
    assert item.next_due == date(2026, 11, 5)


def test_monthly_price_hike_detected() -> None:
    txns = [
        _txn("2026-08-10T09:00:00", 129900, "DR", 2),
        _txn("2026-09-10T09:00:00", 129900, "DR", 2),
        _txn("2026-10-10T09:00:00", 159900, "DR", 2),
    ]
    result = detect_recurring(txns, as_of=date(2026, 10, 15))
    assert len(result.series) == 1
    item = result.series[0]
    assert item.period_days == 30
    assert item.typical_amount_paise == 129900
    assert item.last_amount_change_paise == 30000


def test_monthly_salary_credit_detected_as_series() -> None:
    txns = [
        _txn(f"2026-{m:02d}-01T10:00:00", 6800000, "CR", 3) for m in (6, 7, 8, 9, 10)
    ]
    result = detect_recurring(txns, as_of=date(2026, 10, 15))
    assert len(result.series) == 1
    item = result.series[0]
    assert item.direction == "CR"
    assert item.next_due == date(2026, 11, 1)  # calendar-month-aware, not flat +30 days


def test_irregular_freelance_credit_falls_back_to_range() -> None:
    txns = [
        _txn("2026-07-03T10:00:00", 500000, "CR", 4),
        _txn("2026-07-19T10:00:00", 1200000, "CR", 4),
        _txn("2026-08-02T10:00:00", 700000, "CR", 4),
        _txn("2026-09-25T10:00:00", 1500000, "CR", 4),
    ]
    result = detect_recurring(txns, as_of=date(2026, 10, 1))
    assert result.series == []
    assert len(result.irregular_inflows) == 1
    inflow = result.irregular_inflows[0]
    assert inflow.amount_low_paise <= 700000 <= inflow.amount_high_paise
    assert inflow.next_inflow_date_low <= inflow.next_inflow_date_high


def test_single_occurrence_merchant_ignored() -> None:
    txns = [_txn("2026-10-01T10:00:00", 25000, "DR", 5)]
    result = detect_recurring(txns, as_of=date(2026, 10, 15))
    assert result.series == []
    assert result.irregular_inflows == []


def test_next_inflow_picks_soonest_across_regular_and_irregular() -> None:
    regular_salary = [
        _txn(f"2026-{m:02d}-01T10:00:00", 6800000, "CR", 3) for m in (6, 7, 8, 9, 10)
    ]
    irregular_freelance = [
        _txn("2026-07-03T10:00:00", 500000, "CR", 4),
        _txn("2026-07-19T10:00:00", 1200000, "CR", 4),
        _txn("2026-10-02T10:00:00", 700000, "CR", 4),
    ]
    result = detect_recurring(
        regular_salary + irregular_freelance, as_of=date(2026, 10, 15)
    )
    soonest = result.next_inflow()
    assert soonest is not None
    # the irregular freelance gap (16 days -> 10th pct) lands before the 1st of next month
    assert soonest in result.irregular_inflows


def test_variable_transactions_excludes_recurring_and_irregular() -> None:
    subscription = [
        _txn(f"2026-10-{d:02d}T10:00:00", 11900, "DR", 1, txn_id=d)
        for d in (1, 8, 15, 22, 29)
    ]
    one_off_coffee = _txn("2026-10-10T09:00:00", 15000, "DR", 9, txn_id=100)
    freelance = [
        _txn("2026-07-03T10:00:00", 500000, "CR", 4, txn_id=201),
        _txn("2026-07-19T10:00:00", 1200000, "CR", 4, txn_id=202),
        _txn("2026-08-02T10:00:00", 700000, "CR", 4, txn_id=203),
        _txn("2026-09-25T10:00:00", 1500000, "CR", 4, txn_id=204),
    ]
    all_txns = subscription + [one_off_coffee] + freelance
    result = detect_recurring(all_txns, as_of=date(2026, 11, 1))
    variable = variable_transactions(all_txns, result)
    assert variable == [one_off_coffee]


def test_opposite_direction_outlier_does_not_pollute_series() -> None:
    txns = [
        _txn(f"2026-10-{d:02d}T10:00:00", 11900, "DR", 6) for d in (1, 8, 15, 22, 29)
    ]
    txns.append(
        _txn("2026-10-16T10:00:00", 11900, "CR", 6)
    )  # a one-off refund, same merchant
    result = detect_recurring(txns, as_of=date(2026, 11, 1))
    assert len(result.series) == 1
    assert result.series[0].direction == "DR"
    assert result.series[0].occurrences == 5
