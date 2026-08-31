from __future__ import annotations

import pandas as pd
import pytest

from src.earnings import EPS_SOURCE
from src.manual_eps import derive_manual_eps_ttm_safe, find_prior_year_diluted_eps
from src.quarterly_eps import DILUTED_METRIC, MANUAL_METRIC, REPORTED_METRIC


def _quarterly_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "ABB.ST",
                "period_end": "2025-06-30",
                "report_date": "2025-07-17",
                "observed_date": "2026-08-31",
                "metric": REPORTED_METRIC,
                "eps": 0.61,
                "eps_currency": "USD",
                "source": "Yahoo Finance / Reported EPS",
            },
            {
                "ticker": "ABB.ST",
                "period_end": "2025-06-30",
                "report_date": "",
                "observed_date": "2026-08-31",
                "metric": DILUTED_METRIC,
                "eps": 0.63,
                "eps_currency": "USD",
                "source": "Yahoo Finance / quarterlyDilutedEPS",
            },
            {
                "ticker": "ABB.ST",
                "period_end": "2025-06-30",
                "report_date": "2025-07-17",
                "observed_date": "2026-08-31",
                "metric": MANUAL_METRIC,
                "eps": 0.64,
                "eps_currency": "USD",
                "source": "Bolagets rapport",
            },
        ]
    )


def _earnings_rows(currency: str = "USD") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "ABB.ST",
                "period_end": "2026-03-31",
                "report_date": "2026-04-23",
                "observed_date": "2026-04-23",
                "eps_ttm": 2.72,
                "eps_currency": currency,
                "source": EPS_SOURCE,
            }
        ]
    )


def test_prior_year_selection_prefers_manual_verified_eps() -> None:
    row = find_prior_year_diluted_eps("ABB.ST", "2026-06-30", _quarterly_rows())

    assert row is not None
    assert row["metric"] == MANUAL_METRIC
    assert row["eps"] == pytest.approx(0.64)


def test_manual_period_eps_derives_new_ttm() -> None:
    result = derive_manual_eps_ttm_safe(
        ticker="ABB.ST",
        period_end="2026-06-30",
        current_period_eps=0.68,
        quarterly_frame=_quarterly_rows(),
        earnings_frame=_earnings_rows(),
    )

    assert result["eps_ttm"] == pytest.approx(2.76)
    assert result["prior_year_eps"] == pytest.approx(0.64)
    assert result["eps_currency"] == "USD"
    assert "manual_quarterly_eps_derived_v1" in result["audit_note"]


def test_reported_eps_alone_is_not_accepted_as_diluted_component() -> None:
    reported_only = _quarterly_rows().loc[lambda frame: frame["metric"] == REPORTED_METRIC]

    row = find_prior_year_diluted_eps("ABB.ST", "2026-06-30", reported_only)

    assert row is None
    with pytest.raises(ValueError, match="Yahoo Reported EPS används inte"):
        derive_manual_eps_ttm_safe(
            ticker="ABB.ST",
            period_end="2026-06-30",
            current_period_eps=0.68,
            quarterly_frame=reported_only,
            earnings_frame=_earnings_rows(),
        )


def test_derivation_stops_on_currency_conflict() -> None:
    with pytest.raises(ValueError, match="Valutakonflikt"):
        derive_manual_eps_ttm_safe(
            ticker="ABB.ST",
            period_end="2026-06-30",
            current_period_eps=0.68,
            quarterly_frame=_quarterly_rows(),
            earnings_frame=_earnings_rows(currency="SEK"),
        )


def test_derivation_stops_when_prior_year_period_is_missing() -> None:
    with pytest.raises(ValueError, match="Saknar sparad utspädd EPS"):
        derive_manual_eps_ttm_safe(
            ticker="ABB.ST",
            period_end="2026-09-30",
            current_period_eps=0.70,
            quarterly_frame=_quarterly_rows(),
            earnings_frame=_earnings_rows(),
        )
