from pathlib import Path

import pandas as pd

from src.apply_tradingview_eps_overrides import _apply_history


def test_history_override_skips_cross_currency_reference(tmp_path: Path):
    history_file = tmp_path / "eps_ttm_history.csv"
    pd.DataFrame(
        [
            {
                "ticker": "ABB",
                "report_period": "2026-Q2",
                "report_date": "2026-07-16",
                "eps_ttm": 2.75,
                "currency": "USD",
            },
            {
                "ticker": "DYVOX",
                "report_period": "2026-Q2",
                "report_date": "2026-07-22",
                "eps_ttm": 2.12,
                "currency": "SEK",
            },
        ]
    ).to_csv(history_file, index=False)
    overrides = pd.DataFrame(
        [
            {
                "ticker": "ABB",
                "report_period": "2026-Q2",
                "report_date": pd.Timestamp("2026-07-16"),
                "eps_ttm": 26.4067,
                "currency": "SEK",
                "source": "TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
            },
            {
                "ticker": "DYVOX",
                "report_period": "2026-Q2",
                "report_date": pd.Timestamp("2026-07-22"),
                "eps_ttm": 2.1177,
                "currency": "SEK",
                "source": "TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
            },
        ]
    )

    applied, skipped = _apply_history(overrides, history_file)
    result = pd.read_csv(history_file, encoding="utf-8-sig").set_index("ticker")

    assert (applied, skipped) == (1, 1)
    assert result.loc["ABB", "eps_ttm"] == 2.75
    assert result.loc["ABB", "currency"] == "USD"
    assert result.loc["DYVOX", "eps_ttm"] == 2.1177
    assert result.loc["DYVOX", "currency"] == "SEK"
