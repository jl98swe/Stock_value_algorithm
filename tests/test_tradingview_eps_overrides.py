from pathlib import Path

import pandas as pd

from src.apply_tradingview_eps_overrides import _apply_history, _apply_reports, _load_overrides


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
            {
                "ticker": "ABB",
                "report_period": "2026-Q3",
                "report_date": "",
                "eps_ttm": 2.75,
                "currency": "USD",
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
    assert not ((rows["ticker"] == "ABB") & (rows["report_period"] == "2026-Q3")).any()
    assert result.loc["ABB", "eps_ttm"] == 2.75
    assert result.loc["ABB", "currency"] == "USD"
    assert result.loc["DYVOX", "eps_ttm"] == 2.1177
    assert result.loc["DYVOX", "currency"] == "SEK"


def test_report_override_preserves_cached_date_when_export_date_is_missing(tmp_path: Path):
    reports_file = tmp_path / "reports.csv"
    cache_file = tmp_path / "eps_report_date_cache.csv"
    pd.DataFrame(
        [
            {
                "ticker": "AAK.ST",
                "period_end": "2019-06-30",
                "report_period": "2019-Q2",
                "effective_date": "",
                "eps_ttm": 5.4952,
                "source": "TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
                "verified": True,
                "verified_at": "2026-09-01T08:00:00+00:00",
            }
        ]
    ).to_csv(reports_file, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "AAK.ST",
                "report_period": "2019-Q2",
                "report_date": "2019-07-16",
            }
        ]
    ).to_csv(cache_file, index=False)
    overrides = pd.DataFrame(
        [
            {
                "ticker": "AAK",
                "report_period": "2019-Q2",
                "period_end": pd.Timestamp("2019-06-30"),
                "report_date": pd.NaT,
                "eps_ttm": 5.4952,
                "currency": "SEK",
                "source": "TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
                "report_date_status": "missing",
            }
        ]
    )

    _apply_reports(
        overrides,
        {"AAK": "AAK.ST"},
        reports_file=reports_file,
        cache_file=cache_file,
    )

    result = pd.read_csv(reports_file, dtype=str)
    assert result.loc[0, "effective_date"] == "2019-07-16"
    assert result.loc[0, "verified_at"] == "2026-09-01T08:00:00+00:00"
    assert "effective_date=existing_canonical" in result.loc[0, "notes"]
