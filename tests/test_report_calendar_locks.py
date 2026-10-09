"""Synthetic examples of report locks across truncated price history."""

import pandas as pd
import pytest

from src.events import build_lock_series, load_report_calendar


def _locks(days, scheduled, *, period=None, explicit=None, reports=None):
    calendar = pd.DataFrame([dict(
        ticker="EXAMPLE.ST", report_period=period,
        scheduled_at=pd.Timestamp(scheduled),
        lock_from_date=pd.Timestamp(explicit) if explicit else pd.NaT,
    )])
    if reports is None:
        reports = pd.DataFrame(columns=[
            "ticker", "verified", "published_at", "effective_date",
        ])
    return build_lock_series(pd.Series(pd.to_datetime(days)), "EXAMPLE.ST",
                             [], [], reports, calendar)


@pytest.mark.parametrize("scheduled", [
    "2026-11-17T07:00:00+01:00", "2026-11-17T18:00:00+01:00",
])
def test_distant_future_report_does_not_lock_latest_price(scheduled):
    result = _locks(["2026-10-07", "2026-10-08"], scheduled)
    assert result.FundamentalLock.tolist() == [False, False]
    assert result.LockReason.tolist() == ["", ""]


def test_next_morning_report_locks_previous_close_and_clears_on_verified_eps():
    reports = pd.DataFrame([dict(
        ticker="EXAMPLE.ST", verified=True,
        published_at=pd.Timestamp("2026-11-17T07:05:00+01:00"),
        effective_date=pd.Timestamp("2026-11-17"),
    )])
    result = _locks(["2026-11-13", "2026-11-16", "2026-11-17"],
                    "2026-11-17T07:00:00+01:00", reports=reports)
    assert result.FundamentalLock.tolist() == [False, True, False]
    assert result.LockReason.iloc[1] == "Rapport väntas – EPS måste verifieras"


def test_evening_report_does_not_lock_previous_close():
    result = _locks(["2026-11-16", "2026-11-17"],
                    "2026-11-17T18:00:00+01:00", period="2026-Q3")
    assert result.FundamentalLock.tolist() == [False, True]
    assert result.LockReason.iloc[1] == "Rapport 2026-Q3 väntas – EPS måste verifieras"


def test_monday_report_locks_friday_even_without_report_day_price():
    result = _locks(["2026-10-08", "2026-10-09"],
                    "2026-10-12T07:00:00+02:00")
    assert result.FundamentalLock.tolist() == [False, True]


def test_exchange_holiday_does_not_shift_lock_to_last_observed_price():
    # Stockholm is closed on Good Friday and Easter Monday.
    result = _locks(["2026-04-01", "2026-04-02"],
                    "2026-04-07T07:00:00+02:00")
    assert result.FundamentalLock.tolist() == [False, True]
    result = _locks(["2026-04-01"], "2026-04-07T07:00:00+02:00")
    assert not result.FundamentalLock.any()


def test_explicit_lock_date_still_wins():
    result = _locks(["2026-10-07", "2026-10-08"],
                    "2026-11-17T07:00:00+01:00", explicit="2026-10-08")
    assert result.FundamentalLock.tolist() == [False, True]


def test_empty_calendar_period_is_normalised(tmp_path):
    path = tmp_path / "calendar.csv"
    path.write_text("ticker,scheduled_at,report_period\nEXAMPLE.ST,2026-11-17,\n")
    result = load_report_calendar(path)
    assert result.report_period.tolist() == [""]
