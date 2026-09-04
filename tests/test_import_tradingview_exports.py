from pathlib import Path

import pandas as pd

from src import import_tradingview_exports as module


def test_current_quarter_duplicate_is_dropped_but_changed_value_is_kept(
    tmp_path: Path,
    monkeypatch,
):
    mapping = pd.DataFrame(
        [
            {"borsdata_ticker": "DUP", "tradingview_symbol": "OMXSTO:DUP", "yahoo_ticker": "DUP.ST"},
            {"borsdata_ticker": "NEW", "tradingview_symbol": "OMXSTO:NEW", "yahoo_ticker": "NEW.ST"},
        ]
    )
    stocks = pd.DataFrame(
        [
            {"ticker": "DUP.ST", "price_currency": "SEK"},
            {"ticker": "NEW.ST", "price_currency": "SEK"},
        ]
    )
    mapping_file = tmp_path / "mapping.csv"
    stocks_file = tmp_path / "stocks.csv"
    reports_file = tmp_path / "reports.csv"
    existing_file = tmp_path / "overrides.csv"
    mapping.to_csv(mapping_file, index=False)
    stocks.to_csv(stocks_file, index=False)
    pd.DataFrame(columns=["ticker", "period_end", "effective_date"]).to_csv(reports_file, index=False)
    pd.DataFrame(columns=["ticker", "report_period", "report_date"]).to_csv(existing_file, index=False)
    monkeypatch.setattr(module, "MAPPING_FILE", mapping_file)
    monkeypatch.setattr(module, "STOCKS_FILE", stocks_file)
    monkeypatch.setattr(module, "REPORTS_FILE", reports_file)
    monkeypatch.setattr(module, "EXISTING_OVERRIDES_FILE", existing_file)

    pd.DataFrame(
        {
            "time": ["2026-04-01", "2026-07-01"],
            "close": [10, 11],
            "Diluted EPS TTM": [2.0, 2.0],
        }
    ).to_csv(tmp_path / "OMXSTO_DLY_DUP, 3M.csv", index=False)
    pd.DataFrame(
        {
            "time": ["2026-04-01", "2026-07-01"],
            "close": [10, 11],
            "Diluted EPS TTM": [2.0, 2.5],
        }
    ).to_csv(tmp_path / "OMXSTO_DLY_NEW, 3M.csv", index=False)

    overrides, audit = module.build_overrides(
        [tmp_path], as_of_date=pd.Timestamp("2026-09-04"), first_period="2026-Q2"
    )

    assert overrides.loc[overrides["ticker"] == "DUP", "report_period"].tolist() == ["2026-Q2"]
    assert overrides.loc[overrides["ticker"] == "NEW", "report_period"].tolist() == [
        "2026-Q2",
        "2026-Q3",
    ]
    actions = audit.set_index("ticker")["current_quarter_action"].to_dict()
    assert actions == {"DUP": "dropped_unchanged", "NEW": "kept_changed"}
    current_new = overrides.loc[
        (overrides["ticker"] == "NEW") & (overrides["report_period"] == "2026-Q3")
    ].iloc[0]
    assert current_new["report_date"] == pd.Timestamp("2026-09-04")
    assert current_new["report_date_status"] == "observed_in_export"


def test_historical_identical_quarters_are_retained(tmp_path: Path, monkeypatch):
    mapping = pd.DataFrame(
        [{"borsdata_ticker": "SAME", "tradingview_symbol": "OMXSTO:SAME", "yahoo_ticker": "SAME.ST"}]
    )
    stocks = pd.DataFrame([{"ticker": "SAME.ST", "price_currency": "SEK"}])
    mapping.to_csv(tmp_path / "mapping.csv", index=False)
    stocks.to_csv(tmp_path / "stocks.csv", index=False)
    pd.DataFrame(columns=["ticker", "period_end", "effective_date"]).to_csv(
        tmp_path / "reports.csv", index=False
    )
    pd.DataFrame(columns=["ticker", "report_period", "report_date"]).to_csv(
        tmp_path / "overrides.csv", index=False
    )
    monkeypatch.setattr(module, "MAPPING_FILE", tmp_path / "mapping.csv")
    monkeypatch.setattr(module, "STOCKS_FILE", tmp_path / "stocks.csv")
    monkeypatch.setattr(module, "REPORTS_FILE", tmp_path / "reports.csv")
    monkeypatch.setattr(module, "EXISTING_OVERRIDES_FILE", tmp_path / "overrides.csv")
    pd.DataFrame(
        {
            "time": ["2025-01-02", "2025-04-01", "2025-07-01"],
            "close": [10, 11, 12],
            "Diluted EPS TTM": [3.0, 3.0, 4.0],
        }
    ).to_csv(tmp_path / "SAME_3M.csv", index=False)

    overrides, _ = module.build_overrides(
        [tmp_path], as_of_date=pd.Timestamp("2026-09-04"), first_period="2025-Q1"
    )

    assert overrides["eps_ttm"].tolist() == [3.0, 3.0, 4.0]
