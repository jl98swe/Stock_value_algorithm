"""Synthetic examples and direct parity against the supplied Pine tree arrays."""
import json
import re

import numpy as np
import pandas as pd
import pytest

from src.config import ROOT
from src.model_data import ensure_gbm_model
from src.valuation import GBMModel, calculate_valuation


def example_frame(periods=360):
    x = np.arange(periods, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2025-01-02", periods=periods),
        "Close": 100 + .08*x + 8*np.sin(x/11) + 2*np.sin(x/3.7),
        "EPS_TTM": np.where((x >= 210) & (x < 280), -4., 5.),
    })


def test_negative_model_matches_pine_arrays():
    pine = (ROOT / "reference/test_vard_algo_3_01_diluted.pine").read_text()
    arrays = {key: json.loads("[" + re.search(
        rf"negpe_{key}_arr = array.from\(([^)]*)\)", pine
    ).group(1) + "]") for key in ["ts", "l", "r", "f", "t", "v"]}
    model = GBMModel.load(ROOT / "data/model/negpe_gbm_model.json")
    assert model.feature_count == 6
    assert len(model.tree_root) == 30
    assert len(model.node_feat) == 390
    for features in np.random.default_rng(42).uniform(-100, 100, (100, 6)):
        expected = 0.
        for root in arrays["ts"]:
            node = root
            while arrays["f"][node] >= 0:
                feature = features[arrays["f"][node]]
                node = arrays["l"][node] if feature <= arrays["t"][node] else arrays["r"][node]
            expected += arrays["v"][node]
        assert model.evaluate(features) == expected
    assert '"EARNINGS_PER_SHARE_DILUTED", "TTM"' in pine


def test_transitions_preserve_positive_regression_values():
    result = calculate_valuation(example_frame(), model=GBMModel.load(ensure_gbm_model()))
    # Snapshots from the original 100-tree implementation before this change.
    for index, expected in {200: 45.408373610145055, 330: 24.314291194176636, 359: 100.}.items():
        assert result.loc[index, "Score"] == expected
        assert result.loc[index, "ValuationModel"] == "positive_pe_gbm"
    assert result.loc[[280, 285, 300], "Score"].isna().all()
    negative = result["PE_TTM"].lt(0)
    assert result.loc[negative, "CanRunNegPEGBM"].all()
    assert result.loc[negative, "Score"].equals(result.loc[negative, "NegPEScore"])
    assert result.loc[negative, "ValuationModel"].eq("negative_pe_gbm").all()
    assert not result.loc[negative, "CanRunPositivePEGBM"].any()
    assert result.loc[~result["CanRunGBM"], "Score"].isna().all()


def test_negative_warmup_does_not_use_linear_fallback_or_require_180_days():
    frame = example_frame(100)
    frame["EPS_TTM"] = -4.
    result = calculate_valuation(frame, model=GBMModel.load(ensure_gbm_model()))
    assert result.loc[:37, "Score"].isna().all()
    assert result.loc[38:, "CanRunNegPEGBM"].all()
    assert result.loc[38:, "Score"].between(0, 100).all()
    assert result["PctLong180"].isna().all()
    assert result.loc[38:, "GapPct"].notna().all()
    flat = frame.copy()
    flat["Close"] = 100.
    assert calculate_valuation(flat)["Score"].isna().all()


def test_migration_keeps_positive_scores_and_removes_invalid_negative_scores():
    from src.migrate_negative_pe_scores import migrate
    from src.score_history import normalise_score_history
    history = normalise_score_history(pd.DataFrame({
        "ticker": ["EXAMPLE.ST"] * 4,
        "date": pd.date_range("2026-01-01", periods=4),
        "score": [10., 20., 30., 40.],
        "frozen_at": ["old"] * 4,
    }))
    reports = pd.DataFrame({
        "ticker": ["EXAMPLE.ST"] * 3,
        "period_end": ["2025-09-30", "2025-12-31", "2026-01-03"],
        "effective_date": ["2026-01-01", "2026-01-02", "2026-01-04"],
        "eps_ttm": [5., -4., 6.],
        "report_period": ["2025-Q3", "2025-Q4", "2026-Q1"],
        "verified": [True] * 3,
    })
    rebuilt = history.iloc[[2]].copy()
    rebuilt["score"] = 85.
    result = migrate(history, rebuilt, reports)
    assert result["score"].tolist() == [10., 85., 40.]
    # Invalid negative warmup on January 2 is removed; positives unchanged.
    pd.testing.assert_frame_equal(result.iloc[[0, 2]].reset_index(drop=True), history.iloc[[0, 3]].reset_index(drop=True))
