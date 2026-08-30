import pytest

from src.fetch_data import load_price_history
from src.fundamentals import (
    TV_PERIOD_END_STATE,
    attach_eps_ttm,
    load_reports,
    valuation_calculation_mode,
)
from src.model_data import ensure_gbm_model
from src.valuation import GBMModel, calculate_valuation


def test_dyvox_tv_timing_reproduces_verified_2026_08_28_score():
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

    assert mode == TV_PERIOD_END_STATE
    working = attach_eps_ttm(prices, ticker, reports, calculation_mode=mode)
    valued = calculate_valuation(
        working,
        model=GBMModel.load(ensure_gbm_model()),
    )

    assert valued.iloc[-1]["EPS_TTM"] == pytest.approx(2.1177)
    assert valued.iloc[-1]["Score"] == pytest.approx(86.5390213221, abs=1e-8)
