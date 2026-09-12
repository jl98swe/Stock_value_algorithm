import pytest

from src.fetch_data import load_price_history
from src.fundamentals import (
    REPORT_DATE_STATE,
    attach_eps_ttm,
    load_reports,
    valuation_calculation_mode,
)
from src.model_data import ensure_gbm_model
from src.valuation import GBMModel, calculate_valuation


def test_dyvox_uses_report_dates_and_only_scores_when_gbm_can_run():
    ticker = "DYVOX.ST"
    prices = load_price_history()
    prices = prices.loc[
        (prices["ticker"] == ticker) & (prices["date"] <= "2026-08-28")
    ].rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    reports = load_reports()
    mode = valuation_calculation_mode(ticker, reports)

    assert mode == REPORT_DATE_STATE
    working = attach_eps_ttm(prices, ticker, reports, calculation_mode=mode)
    valued = calculate_valuation(
        working,
        model=GBMModel.load(ensure_gbm_model()),
    )

    assert valued.iloc[-1]["EPS_TTM"] == pytest.approx(2.1177)
    assert valued.loc[~valued["CanRunGBM"], "Score"].isna().all()
    assert valued.loc[valued["CanRunGBM"], "Score"].notna().all()


def test_abb_tv_values_stay_in_sek_but_use_report_date_timing():
    ticker = "ABB.ST"
    prices = load_price_history()
    prices = prices.loc[
        (prices["ticker"] == ticker) & (prices["date"] <= "2026-08-28")
    ].rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    reports = load_reports()
    mode = valuation_calculation_mode(ticker, reports)
    abb_reports = reports.loc[
        (reports["ticker"] == ticker)
        & reports["source"].astype(str).str.startswith("TradingView")
    ].sort_values("period_end")

    assert mode == REPORT_DATE_STATE
    assert len(abb_reports) == 32
    assert abb_reports.iloc[0]["report_period"] == "2018-Q3"
    working = attach_eps_ttm(prices, ticker, reports, calculation_mode=mode)
    valued = calculate_valuation(
        working,
        model=GBMModel.load(ensure_gbm_model()),
    )

    assert working.iloc[-1]["EPS_TTM_RAW"] == pytest.approx(26.4067)
    assert working.iloc[-1]["EPS_CURRENCY"] == "SEK"
    assert working.iloc[-1]["FX_RATE"] == pytest.approx(1.0)
    assert valued.iloc[-1]["EPS_TTM"] == pytest.approx(26.4067)
    assert valued.loc[~valued["CanRunGBM"], "Score"].isna().all()
    assert valued.loc[valued["CanRunGBM"], "Score"].notna().all()
    assert valued.loc[valued["Score"].notna(), "Date"].iloc[0] == valued.loc[
        valued["CanRunGBM"], "Date"
    ].iloc[0]
