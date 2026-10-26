from __future__ import annotations

import pandas as pd

from src import build_yahoo_history_all


def test_extend_metadata_preserves_tickers_without_new_yahoo_history(tmp_path, monkeypatch):
    metadata_file = tmp_path / "stocks_yahoo.csv"
    pd.DataFrame(
        [
            {
                "ticker": "VIVA.ST",
                "company": "Viva Wine Group AB",
                "isin": "",
                "price_currency": "SEK",
                "report_currency": "SEK",
            }
        ]
    ).to_csv(metadata_file, index=False)
    monkeypatch.setattr(build_yahoo_history_all, "METADATA_FILE", metadata_file)
    monkeypatch.setattr(build_yahoo_history_all, "_fetch_price_currency", lambda ticker: "SEK")

    history = pd.DataFrame(
        [
            {
                "ticker": "COOR.ST",
                "as_of_date": "2026-09-30",
                "currency_code": "SEK",
            }
        ]
    )

    result = build_yahoo_history_all._extend_metadata(history, workers=1)

    assert result["ticker"].tolist() == ["COOR.ST", "VIVA.ST"]
    viva = result.loc[result["ticker"] == "VIVA.ST"].iloc[0]
    assert viva["company"] == "Viva Wine Group AB"
    assert viva["report_currency"] == "SEK"
