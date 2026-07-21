"""Shared time helpers: duration formatting and local-day period bounds."""

import datetime

PERIODS = ["Today", "Last 7 days", "This month"]


def fmt_hm(seconds):
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}"


def fmt_hms(seconds):
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def period_bounds(period):
    """(start_ts, end_ts) of a named period, on real local midnights (DST-safe)."""
    today = datetime.date.today()
    if period == "Last 7 days":
        start = today - datetime.timedelta(days=6)
    elif period == "This month":
        start = today.replace(day=1)
    else:
        start = today
    s = datetime.datetime.combine(start, datetime.time.min).timestamp()
    e = datetime.datetime.combine(
        today + datetime.timedelta(days=1), datetime.time.min).timestamp()
    return s, e
