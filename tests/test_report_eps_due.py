from __future__ import annotations

import pandas as pd

import src.report_eps_due as due
from src.quarterly_eps import DILUTED_METRIC


def _calendar(*args, **kwargs) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ticker": "DUE.ST",
            "report_date_start": "2026-09-17",
            "report_date_end": "2026-09-17",
            "observed_date": "2026-09-13",
        },
        {
            "ticker": "DONE.ST",
            "report_date_start": "2026-09-16",
            "report_date_end": "2026-09-16",
            "observed_date": "2026-09-13",
        },
        {
            "ticker": "FUTURE.ST",
            "report_date_start": "2026-09-18",
            "report_date_end": "2026-09-18",
            "observed_date": "2026-09-13",
        },
    ])


def test_ttm_polling_starts_on_report_day_and_stops_after_new_period(monkeypatch) -> None:
    monkeypatch.setattr(due, "load_auto_report_calendar", _calendar)
    monkeypatch.setattr(due, "load_earnings_history", lambda: pd.DataFrame([
        {"ticker": "DUE.ST", "period_end": "2026-06-30", "observed_date": "2026-07-20"},
        {"ticker": "DONE.ST", "period_end": "2026-06-30", "observed_date": "2026-07-20"},
        {"ticker": "DONE.ST", "period_end": "2026-09-30", "observed_date": "2026-09-17"},
    ]))

    assert due.pending_ttm_tickers("2026-09-17") == ["DUE.ST"]


def test_quarterly_polling_ignores_non_comparable_reported_eps(monkeypatch) -> None:
    monkeypatch.setattr(due, "load_auto_report_calendar", _calendar)
    monkeypatch.setattr(due, "load_quarterly_eps", lambda: pd.DataFrame([
        {"ticker": "DUE.ST", "period_end": "2026-06-30", "observed_date": "2026-07-20", "metric": DILUTED_METRIC},
        {"ticker": "DUE.ST", "period_end": "2026-09-30", "observed_date": "2026-09-17", "metric": "reportedEPS"},
        {"ticker": "DONE.ST", "period_end": "2026-06-30", "observed_date": "2026-07-20", "metric": DILUTED_METRIC},
        {"ticker": "DONE.ST", "period_end": "2026-09-30", "observed_date": "2026-09-17", "metric": DILUTED_METRIC},
    ]))

    assert due.pending_quarterly_tickers("2026-09-17") == ["DUE.ST"]
