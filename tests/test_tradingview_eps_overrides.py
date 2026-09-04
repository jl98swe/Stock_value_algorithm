from pathlib import Path

import pandas as pd

from src.apply_tradingview_eps_overrides import _apply_history, _load_overrides


def test_abb_override_history_covers_2018_q3_through_2026_q2():
    overrides = _load_overrides()
    abb = overrides.loc[overrides["ticker"] == "ABB"].sort_values("report_period")

    assert len(abb) == 32
    assert abb.iloc[0]["report_period"] == "2018-Q3"
    assert abb.iloc[-1]["report_period"] == "2026-Q2"
    assert abb["period_end"].notna().all()


def test_all_tickers_have_tradingview_history_and_current_duplicates_are_removed():
    overrides = _load_overrides()
    mapping = pd.read_csv("config/ticker_mapping.csv", encoding="utf-8-sig")

    assert overrides["ticker"].nunique() == len(mapping)
    assert set(overrides["ticker"]) == set(mapping["borsdata_ticker"])
    latest = overrides.sort_values("period_end").groupby("ticker").tail(1)
    assert latest["report_period"].value_counts().to_dict() == {"2026-Q2": 117, "2026-Q3": 2}


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
                "report_period": "2018-Q3",
                "report_date": pd.Timestamp("2018-10-25"),
                "eps_ttm": 9.3457,
                "currency": "SEK",
                "source": "TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
            },
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

    assert (applied, skipped) == (1, 2)
    rows = result.reset_index()
    assert not ((rows["ticker"] == "ABB") & (rows["report_period"] == "2018-Q3")).any()
    assert result.loc["ABB", "eps_ttm"] == 2.75
    assert result.loc["ABB", "currency"] == "USD"
    assert result.loc["DYVOX", "eps_ttm"] == 2.1177
    assert result.loc["DYVOX", "currency"] == "SEK"
