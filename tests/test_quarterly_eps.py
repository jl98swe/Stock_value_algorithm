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
        reports_frame=pd.DataFrame(),
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
            reports_frame=pd.DataFrame(),
        )


def test_derivation_stops_on_currency_conflict() -> None:
    with pytest.raises(ValueError, match="Valutakonflikt"):
        derive_manual_eps_ttm_safe(
            ticker="ABB.ST",
            period_end="2026-06-30",
            current_period_eps=0.68,
            quarterly_frame=_quarterly_rows(),
            earnings_frame=_earnings_rows(currency="SEK"),
            reports_frame=pd.DataFrame(),
        )


def test_derivation_stops_when_prior_year_period_is_missing() -> None:
    with pytest.raises(ValueError, match="Saknar sparad utspädd EPS"):
        derive_manual_eps_ttm_safe(
            ticker="ABB.ST",
            period_end="2026-09-30",
            current_period_eps=0.70,
            quarterly_frame=_quarterly_rows(),
            earnings_frame=_earnings_rows(),
            reports_frame=pd.DataFrame(),
        )


def _manual_ttm(value: float = 2.70, currency: str = "USD", *, verified=True,
                period: str = "2026-03-31") -> pd.DataFrame:
    return pd.DataFrame([dict(
        ticker="ABB.ST", period_end=period, report_period="2026-Q1",
        effective_date="2026-04-23", eps_ttm=value,
        source="TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
        verified=verified, verified_at="2026-04-24T00:00:00Z",
        notes=f"tradingview_eps_manual_override_v1; report_currency={currency}",
    )])


def test_verified_tv_base_beats_later_yahoo_observation() -> None:
    yahoo = _earnings_rows()
    yahoo["observed_date"] = "2026-05-20"
    result = derive_manual_eps_ttm_safe(
        ticker="ABB.ST", period_end="2026-06-30", current_period_eps=.68,
        quarterly_frame=_quarterly_rows(), earnings_frame=yahoo,
        reports_frame=_manual_ttm(),
    )
    assert result["eps_ttm"] == pytest.approx(2.74)
    assert result["previous_ttm"] == 2.70
    assert result["previous_ttm_kind"] == "manual_tradingview"
    assert "previous_ttm_source=TradingView" in result["audit_note"]


def test_verified_tv_base_works_without_yahoo() -> None:
    result = derive_manual_eps_ttm_safe(
        ticker="ABB.ST", period_end="2026-06-30", current_period_eps=.68,
        quarterly_frame=_quarterly_rows(), earnings_frame=pd.DataFrame(),
        reports_frame=_manual_ttm(),
    )
    assert result["eps_ttm"] == pytest.approx(2.74)


@pytest.mark.parametrize("manual", [
    _manual_ttm(verified=False),
    _manual_ttm(period="2025-12-31"),
    _manual_ttm(period="2026-06-30"),
])
def test_unverified_older_or_current_period_tv_does_not_replace_previous_quarter(manual) -> None:
    result = derive_manual_eps_ttm_safe(
        ticker="ABB.ST", period_end="2026-06-30", current_period_eps=.68,
        quarterly_frame=_quarterly_rows(), earnings_frame=_earnings_rows(),
        reports_frame=manual,
    )
    assert result["eps_ttm"] == pytest.approx(2.76)
    assert result["previous_ttm_kind"] == "yahoo_trailing_diluted"


def test_tv_currency_conflict_stops_instead_of_silently_falling_back_to_yahoo() -> None:
    with pytest.raises(ValueError, match="Valutakonflikt"):
        derive_manual_eps_ttm_safe(
            ticker="ABB.ST", period_end="2026-06-30", current_period_eps=.68,
            quarterly_frame=_quarterly_rows(), earnings_frame=_earnings_rows(),
            reports_frame=_manual_ttm(currency="SEK"),
        )


def test_legacy_entry_point_obeys_tv_priority_and_diluted_metric() -> None:
    from src.quarterly_eps import derive_manual_eps_ttm
    result = derive_manual_eps_ttm(
        ticker="ABB.ST", period_end="2026-06-30", current_quarter_eps=.68,
        quarterly_frame=_quarterly_rows(), earnings_frame=_earnings_rows(),
        reports_frame=_manual_ttm(),
    )
    assert result["eps_ttm"] == pytest.approx(2.74)
