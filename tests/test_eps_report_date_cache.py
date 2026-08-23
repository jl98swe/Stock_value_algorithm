from __future__ import annotations

import pandas as pd

from src import enrich_historical_eps as module


def test_cached_report_dates_do_not_shift_when_yahoo_adds_new_report(tmp_path, monkeypatch):
    source_file = tmp_path / "eps_ttm_history.csv"
    mapping_file = tmp_path / "ticker_mapping.csv"
    metadata_file = tmp_path / "stocks.csv"
    output_file = tmp_path / "eps_ttm_history_enriched.csv"
    cache_file = tmp_path / "eps_report_date_cache.csv"
    output_metadata_file = tmp_path / "stocks_yahoo.csv"
    audit_file = tmp_path / "eps_report_date_audit.csv"

    pd.DataFrame(
        [
            {"ticker": "ATT", "report_period": "2025-Q4", "report_date": "", "eps_ttm": 5.49, "currency": "SEK"},
            {"ticker": "ATT", "report_period": "2026-Q1", "report_date": "", "eps_ttm": 5.91, "currency": "SEK"},
            {"ticker": "ATT", "report_period": "2026-Q2", "report_date": "", "eps_ttm": 6.61, "currency": "SEK"},
        ]
    ).to_csv(source_file, index=False)

    pd.DataFrame(
        [
            {
                "borsdata_ticker": "ATT",
                "tradingview_symbol": "OMXSTO:ATT",
                "yahoo_ticker": "ATT.ST",
            }
        ]
    ).to_csv(mapping_file, index=False)

    pd.DataFrame(
        [
            {
                "ticker": "ATT",
                "company": "Attendo",
                "isin": "SE0007666110",
                "price_currency": "SEK",
                "report_currency": "SEK",
            }
        ]
    ).to_csv(metadata_file, index=False)

    pd.DataFrame(
        [
            {"ticker": "ATT.ST", "report_period": "2025-Q4", "report_date": "2026-02-05"},
            {"ticker": "ATT.ST", "report_period": "2026-Q1", "report_date": "2026-05-06"},
        ]
    ).to_csv(cache_file, index=False)

    # Yahoo har hunnit lägga till Q2. Utan cache skulle en ren tail-alignment
    # kunna flytta de två äldre perioderna ett kvartal framåt.
    monkeypatch.setattr(
        module,
        "_past_earnings_dates",
        lambda ticker, wanted: [pd.Timestamp("2026-05-06"), pd.Timestamp("2026-08-20")],
    )

    result = module.enrich(
        source_file=source_file,
        mapping_file=mapping_file,
        output_file=output_file,
        report_date_cache_file=cache_file,
        metadata_file=metadata_file,
        output_metadata_file=output_metadata_file,
        audit_file=audit_file,
    )

    dates = result.set_index("report_period")["report_date"].to_dict()
    assert dates["2025-Q4"] == "2026-02-05"
    assert dates["2026-Q1"] == "2026-05-06"
    assert dates["2026-Q2"] == "2026-08-20"

    cache = pd.read_csv(cache_file, dtype=str)
    cache_dates = cache.set_index("report_period")["report_date"].to_dict()
    assert cache_dates["2025-Q4"] == "2026-02-05"
    assert cache_dates["2026-Q1"] == "2026-05-06"
    assert cache_dates["2026-Q2"] == "2026-08-20"
