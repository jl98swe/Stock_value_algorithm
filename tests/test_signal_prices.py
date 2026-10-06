import numpy as np
import pandas as pd
import pytest

from src.config import ROOT
from src.model_data import ensure_gbm_model
from src.signal_prices import NextCloseScore, find_boundary, write_signal_prices
from src.valuation import GBMModel, calculate_valuation


@pytest.mark.parametrize("eps", [5.0, -5.0])
def test_next_close_matches_full_valuation_for_positive_and_negative_eps(eps):
    # Synthetic history with changing EPS and prices, including all lookbacks.
    dates = pd.bdate_range("2025-01-02", periods=230)
    x = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame({"Date": dates, "Close": 100 + .08 * x + 8 * np.sin(x / 11),
                          "EPS_TTM": eps + .002 * x})
    model = GBMModel.load(ensure_gbm_model())
    negative = GBMModel.load(ROOT / "data/model/negpe_gbm_model.json")
    predict = NextCloseScore(frame, model, negative)
    prices = [90., 110., 130.]
    actual = []
    for price in prices:
        row = frame.iloc[-1:].copy()
        row["Date"] = dates[-1] + pd.offsets.BDay()
        row["Close"] = price
        actual.append(calculate_valuation(pd.concat([frame, row], ignore_index=True),
                      model=model, negative_model=negative).Score.iloc[-1])
    assert np.allclose(predict(prices), actual, atol=1e-8)


def test_nearest_boundary_does_not_assume_monotonic_score():
    # Synthetic curve: buy below 90, then again between 95 and 98.
    predict = lambda x: np.where((np.asarray(x) < 90) | ((np.asarray(x) > 95) & (np.asarray(x) < 98)), .5, 50.)
    result = find_boundary(predict, 100, "buy")
    assert result["price"] == pytest.approx(98, abs=2e-6)
    assert result["direction"] == "below"
    assert result["score"] < 1
    assert result["multiple_crossings"]


def test_unreachable_boundary_and_missing_eps_are_not_fabricated(tmp_path):
    assert find_boundary(lambda x: np.full(len(x), 50.), 100, "buy") is None
    frame = pd.DataFrame({"Date": [pd.Timestamp("2026-10-05")], "Close": [100.], "EPS_TTM": [np.nan]})
    result = write_signal_prices({"TEST": frame}, GBMModel.load(ensure_gbm_model()), "now", tmp_path / "prices.json")
    assert result["stocks"] == {}
