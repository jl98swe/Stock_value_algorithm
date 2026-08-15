import numpy as np
import pandas as pd

from src.model_data import ensure_gbm_model
from src.valuation import GBMModel, calculate_valuation


def test_embedded_gbm_and_score_are_operational():
    dates = pd.bdate_range("2025-01-02", periods=280)
    x = np.arange(len(dates), dtype=float)
    # Varierande men alltid positiv serie så att samtliga Pine-featurefönster
    # hinner bli giltiga efter warmup.
    close = 100.0 + 0.08 * x + 8.0 * np.sin(x / 11.0) + 2.0 * np.sin(x / 3.7)
    eps = 5.0 + 0.002 * x
    frame = pd.DataFrame({"Date": dates, "Close": close, "EPS_TTM": eps})

    model = GBMModel.load(ensure_gbm_model())
    result = calculate_valuation(frame, model=model)

    assert len(model.tree_root) == 100
    assert result["CanRunGBM"].any()
    valid_scores = result["Score"].dropna()
    assert not valid_scores.empty
    assert valid_scores.between(0.0, 100.0).all()
    assert np.isfinite(result.loc[result["CanRunGBM"], "GBMBoost"]).all()
