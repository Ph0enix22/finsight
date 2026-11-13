"""The app has exactly one place where a calendar date needs converting to a
UTC instant range: filtering transactions by day. `settings.as_of_date` and
every `from`/`to` query param on `GET /transactions` mean an Asia/Kolkata
(IST) calendar day — stored timestamps are true UTC (see
scripts/generate.py's IST_OFFSET comment) — so a day boundary must be
computed in IST, not assumed to line up with the UTC day.
"""

from datetime import UTC, date, datetime, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)


def ist_day_start_utc(d: date) -> datetime:
    """The UTC instant at which `d` (an IST calendar day) begins."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC) - IST_OFFSET


def ist_day_end_utc(d: date) -> datetime:
    """The UTC instant at which `d` (an IST calendar day) ends."""
    return datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=UTC) - IST_OFFSET
