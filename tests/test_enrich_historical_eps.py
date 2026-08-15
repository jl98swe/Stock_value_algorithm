from __future__ import annotations

import pandas as pd

from src.enrich_historical_eps import (
    _align_dates,
    _latest_contiguous_quarterly_suffix,
    _period_key,
    _stockholm_calendar_date,
)


def test_period_key_handles_fiscal_year_labels() -> None:
    assert _period_key("2027-Q1") == (2027, 1)
    assert _period_key("2026-Q4") == (2026, 4)


def test_align_dates_matches_oldest_to_oldest_when_complete() -> None:
    periods = ["2024-Q1", "2024-Q2", "2024-Q3"]
    dates = [
        pd.Timestamp("2024-04-25"),
        pd.Timestamp("2024-07-18"),
        pd.Timestamp("2024-10-24"),
    ]

    result = _align_dates(periods, dates)

    assert result["2024-Q1"] == pd.Timestamp("2024-04-25")
    assert result["2024-Q3"] == pd.Timestamp("2024-10-24")


def test_align_dates_anchors_partial_history_at_newest_end() -> None:
    periods = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
    dates = [pd.Timestamp("2024-10-24"), pd.Timestamp("2025-01-30")]

    result = _align_dates(periods, dates)

    assert set(result) == {"2024-Q3", "2024-Q4"}
    assert result["2024-Q4"] == pd.Timestamp("2025-01-30")


def test_large_gap_breaks_older_yahoo_history() -> None:
    dates = [
        pd.Timestamp("2018-08-21"),
        pd.Timestamp("2025-05-06"),
        pd.Timestamp("2025-08-19"),
        pd.Timestamp("2025-11-11"),
        pd.Timestamp("2026-02-17"),
    ]

    result = _latest_contiguous_quarterly_suffix(dates)

    assert result == [
        pd.Timestamp("2025-05-06"),
        pd.Timestamp("2025-08-19"),
        pd.Timestamp("2025-11-11"),
        pd.Timestamp("2026-02-17"),
    ]


def test_missing_quarter_breaks_alignment_instead_of_shifting_periods() -> None:
    dates = [
        pd.Timestamp("2025-10-10"),
        pd.Timestamp("2026-01-30"),
        pd.Timestamp("2026-07-03"),
    ]

    result = _latest_contiguous_quarterly_suffix(dates)

    assert result == [pd.Timestamp("2026-07-03")]


def test_yahoo_us_timezone_is_converted_to_stockholm_date() -> None:
    # Sunday evening in New York can be Monday after midnight in Stockholm.
    value = pd.Timestamp("2026-07-05 19:30:00", tz="America/New_York")

    assert _stockholm_calendar_date(value) == pd.Timestamp("2026-07-06")
