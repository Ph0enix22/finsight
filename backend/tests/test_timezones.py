from datetime import UTC, date, datetime

from app.core.timezones import ist_day_end_utc, ist_day_start_utc


def test_ist_day_bounds_for_as_of_date() -> None:
    d = date(2026, 11, 14)
    # IST is UTC+5:30, so the IST day starts 5:30 "early" in UTC terms and
    # ends 5:30 "early" too — both boundaries fall on the UTC-previous day's
    # evening, not at UTC midnight.
    assert ist_day_start_utc(d) == datetime(2026, 11, 13, 18, 30, tzinfo=UTC)
    assert ist_day_end_utc(d) == datetime(2026, 11, 14, 18, 29, 59, 999999, tzinfo=UTC)


def test_ist_day_end_excludes_the_next_ist_days_early_morning() -> None:
    # 00:15 IST on 15-Nov is 18:45 UTC on 14-Nov — a naive UTC-midnight
    # boundary for "14-Nov" would wrongly include it; the real IST day-end
    # (18:29:59 UTC on 14-Nov) must not.
    fifteenth_nov_0015_ist_in_utc = datetime(2026, 11, 14, 18, 45, tzinfo=UTC)
    assert fifteenth_nov_0015_ist_in_utc > ist_day_end_utc(date(2026, 11, 14))
    assert fifteenth_nov_0015_ist_in_utc <= ist_day_end_utc(date(2026, 11, 15))
