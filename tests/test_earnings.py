from __future__ import annotations

import pandas as pd

from src.earnings import EARNINGS_COLUMNS, _normalise_earnings, _select_latest_report_date


def test_select_latest_past_report_with_reported_eps() -> None:
    dates = pd.DataFrame(
        {
            "EPS Estimate": [1.0, 1.1, 1.2],
            "Reported EPS": [0.9, 1.05, None],
        },
        index=pd.DatetimeIndex(
            [
                "2026-04-23 07:00:00+02:00",
                "2026-07-16 07:00:00+02:00",
                "2026-10-22 07:00:00+02:00",
            ],
            name="Earnings Date",
        ),
    )

    selected = _select_latest_report_date(
        dates,
        now=pd.Timestamp("2026-08-15T09:00:00Z"),
    )

    assert selected == pd.Timestamp("2026-07-16")


def test_future_earnings_date_is_never_selected() -> None:
    dates = pd.DataFrame(
        {"Reported EPS": [1.05, None]},
        index=pd.DatetimeIndex(
            ["2026-07-16 07:00:00+02:00", "2026-10-22 07:00:00+02:00"],
            name="Earnings Date",
        ),
    )

    selected = _select_latest_report_date(
        dates,
        now=pd.Timestamp("2026-08-15T09:00:00Z"),
    )

    assert selected == pd.Timestamp("2026-07-16")


def test_legacy_earnings_file_is_supported_until_metric_migration() -> None:
    legacy = pd.DataFrame(
        [
            {
                "ticker": "AAK.ST",
                "observed_date": "2026-08-15",
                "eps_ttm": 13.82,
                "source": "Yahoo Finance / trailingEps",
            }
        ]
    )

    normalised = _normalise_earnings(legacy)

    assert list(normalised.columns) == EARNINGS_COLUMNS
    assert pd.isna(normalised.loc[0, "period_end"])
    assert pd.isna(normalised.loc[0, "report_date"])
    assert normalised.loc[0, "eps_currency"] == ""


def test_new_diluted_eps_schema_preserves_period_and_currency() -> None:
    frame = pd.DataFrame(
        [
            {
                "ticker": "ABB.ST",
                "period_end": "2026-06-30",
                "report_date": "2026-07-16",
                "observed_date": "2026-08-15",
                "eps_ttm": 2.76,
                "eps_currency": "usd",
                "source": "Yahoo Finance / trailingDilutedEPS",
            }
        ]
    )

    normalised = _normalise_earnings(frame)

    assert normalised.loc[0, "period_end"] == pd.Timestamp("2026-06-30")
    assert normalised.loc[0, "eps_currency"] == "USD"
    assert normalised.loc[0, "eps_ttm"] == 2.76
