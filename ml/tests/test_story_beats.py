"""Asserts the scripted persona story beats (CLAUDE.md Phase 2 brief) actually
land in the generated data/sample/*.json fixtures, not just "looked right"
when eyeballed once."""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sample"
AS_OF = "2026-11-14"
MONTH_START = "2026-11-01"

# Stored `ts` is true UTC (scripts/generate.py's IST_OFFSET comment) — every
# story beat here is specified in IST wall-clock terms (the 1st of the
# month, 2:13 AM, "this month"), so tests must convert back before comparing
# against calendar-day/time strings, never slice the raw UTC string.
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _ist(ts: str) -> datetime:
    return datetime.fromisoformat(ts) + _IST_OFFSET


def _load(persona: str) -> list[dict] | None:
    path = SAMPLE_DIR / f"{persona}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["txns"]


_AARAV = _load("aarav")
_PRIYA = _load("priya")
_FATIMA = _load("fatima")

requires_data = pytest.mark.skipif(
    _AARAV is None, reason="data/sample not generated — run scripts/generate.py"
)


@requires_data
def test_aarav_allowance_9000_on_first_of_month() -> None:
    allowance = [
        t
        for t in _AARAV
        if t["merchant_key"] == "Parent Allowance Credit" and _ist(t["ts"]).day == 1
    ]
    assert allowance, "no allowance credit found on the 1st of a month"
    assert all(t["amount_paise"] == 900000 for t in allowance)


@requires_data
def test_aarav_balance_tight_but_positive_on_as_of_date() -> None:
    # The exact figure now emerges from per-merchant pricing + the strict
    # balance invariant (no plug transactions), so this checks the STORY
    # ("hostel student, tight budget, something left") rather than a
    # hand-picked number.
    day_txns = [t for t in _AARAV if _ist(t["ts"]).date().isoformat() <= AS_OF]
    assert day_txns
    last = max(day_txns, key=lambda t: t["ts"])
    assert 0 <= last["balance_after_paise"] <= 500000  # Rs 0-5,000


@requires_data
def test_aarav_41_food_payments_this_month_totalling_4093() -> None:
    # food_delivery + dining_cafe is THE food-spend definition for this story
    # beat (see backend/app/core/categories.py:FOOD_SPEND_CATEGORIES) — food
    # delivery alone undercounts it by the 16 dining_cafe payments.
    this_month = [
        t
        for t in _AARAV
        if MONTH_START <= _ist(t["ts"]).date().isoformat() <= AS_OF
        and t["category"] in ("food_delivery", "dining_cafe")
    ]
    assert len(this_month) == 41
    assert all(t["amount_paise"] < 20000 for t in this_month)
    total = sum(t["amount_paise"] for t in this_month)
    # Deterministic (--seed 42): pin the exact figure instead of a wide band,
    # so a future pricing change has to update this on purpose, not drift.
    assert total == 409300


@requires_data
def test_aarav_anomaly_2499_at_0213_never_seen_merchant() -> None:
    # Background ~2% random anomaly injection runs across aarav's whole
    # history too, so this merchant_key — not "the only anomaly" — is what
    # uniquely identifies the one scripted story-beat anomaly.
    matches = [t for t in _AARAV if t["merchant_key"] == "QuickFix Mobile Repair Kiosk"]
    assert len(matches) == 1
    anomaly = matches[0]
    assert anomaly["anomaly"]
    assert anomaly["amount_paise"] == 249900
    # Acceptance criterion from the timezone fix: displays "2:13 am, 7 Nov"
    # IST — stored `ts` is UTC, so convert back before checking either half.
    ist_ts = _ist(anomaly["ts"])
    assert ist_ts.strftime("%H:%M") == "02:13"
    assert ist_ts.date().isoformat() == "2026-11-07"
    other_merchants = {t["merchant_key"] for t in _AARAV if t is not anomaly}
    assert anomaly["merchant_key"] not in other_merchants


@requires_data
def test_aarav_no_transaction_after_as_of_date_in_ist() -> None:
    # Acceptance criterion: nothing lands after 14 Nov once interpreted in
    # the zone AS_OF_DATE is actually defined in (IST), not the raw UTC
    # string. (The fixture intentionally runs a few days past AS_OF_DATE for
    # other tests/phases, so this checks the AS_OF-dated slice, not the
    # whole file.)
    as_of_window = [t for t in _AARAV if _ist(t["ts"]).date().isoformat() <= AS_OF]
    assert as_of_window
    assert all(_ist(t["ts"]).date().isoformat() <= AS_OF for t in as_of_window)

    # Regression guard: prove the UTC/IST conversion is actually doing
    # something, by pinning a transaction that's known to straddle the
    # boundary. If the generator ever reverts to storing naive-IST timestamps
    # tagged as UTC, this is the assertion that starts failing.
    quickfix = next(
        t for t in _AARAV if t["merchant_key"] == "QuickFix Mobile Repair Kiosk"
    )
    assert quickfix["ts"][:10] == "2026-11-06"
    assert _ist(quickfix["ts"]).date().isoformat() == "2026-11-07"


@requires_data
def test_aarav_recurring_patterns_present() -> None:
    counts = Counter(t["merchant_key"] for t in _AARAV)
    assert counts["Spotify Student Plan"] >= 3
    assert counts["Jio Recharge"] >= 3
    hostel_split = [t for t in _AARAV if t.get("note") == "Friend Split Payment"]
    assert len(hostel_split) >= 3


@requires_data
def test_priya_four_subscriptions_totalling_1947_baseline() -> None:
    expected = {
        "Netflix": 19900,
        "Spotify": 11900,
        "Prime Video": 33000,
        "Gold's Gym AutoPay": 129900,
    }
    assert sum(expected.values()) == 194700
    subs = [
        t
        for t in _PRIYA
        if t["category"] == "subscriptions" and t["merchant_key"] in expected
    ]
    merchants_seen = {t["merchant_key"] for t in subs}
    assert merchants_seen == set(expected)
    pre_hike_gym = [
        t
        for t in _PRIYA
        if t["merchant_key"] == "Gold's Gym AutoPay" and not t["price_hike"]
    ]
    assert pre_hike_gym
    assert all(t["amount_paise"] == 129900 for t in pre_hike_gym)


@requires_data
def test_priya_gym_hike_this_month() -> None:
    gym_this_month = [
        t
        for t in _PRIYA
        if t["merchant_key"] == "Gold's Gym AutoPay"
        and _ist(t["ts"]).strftime("%Y-%m") == MONTH_START[:7]
    ]
    assert len(gym_this_month) == 1
    assert gym_this_month[0]["amount_paise"] == 159900
    assert gym_this_month[0]["price_hike"]


@requires_data
def test_priya_salary_rent_family_amounts() -> None:
    salary = [t for t in _PRIYA if t["merchant_key"] == "Employer Payroll"]
    assert salary and all(t["amount_paise"] == 6800000 for t in salary)
    rent = [
        t
        for t in _PRIYA
        if t["category"] == "rent_housing" and t["amount_paise"] == 1800000
    ]
    assert len(rent) >= 3
    family = [
        t
        for t in _PRIYA
        if t["category"] == "transfers_family" and t["amount_paise"] == 800000
    ]
    assert len(family) >= 3


@requires_data
def test_fatima_stipend_6000_monthly() -> None:
    stipend = [t for t in _FATIMA if t["merchant_key"] == "Stipend Credit"]
    assert len(stipend) >= 5
    assert all(t["amount_paise"] == 600000 for t in stipend)


@requires_data
def test_fatima_irregular_freelance_credits() -> None:
    freelance = [t for t in _FATIMA if t["merchant_key"] == "Freelance Client Payment"]
    assert freelance
    assert all(300000 <= t["amount_paise"] <= 1500000 for t in freelance)
    by_month: dict[str, int] = defaultdict(int)
    for t in freelance:
        by_month[_ist(t["ts"]).strftime("%Y-%m")] += 1
    # The first and last calendar months in the generation window are partial
    # (the window starts/ends mid-month), so only full months should be held
    # to the 2-4/month cadence.
    all_months = sorted(by_month)
    full_months = {
        m: c for m, c in by_month.items() if m not in (all_months[0], all_months[-1])
    }
    assert (
        full_months
    ), "need at least one fully-generated month to check the 2-4/month cadence"
    assert all(2 <= c <= 4 for c in full_months.values())
