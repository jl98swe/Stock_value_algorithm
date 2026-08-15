from __future__ import annotations

import pandas as pd

from src.enrich_historical_eps import _align_dates, _period_key


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
