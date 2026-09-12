from pathlib import Path

import pandas as pd

from src.apply_report_date_overrides import apply_overrides


def test_override_can_seed_cache_for_report_missing_from_enriched_history(tmp_path: Path):
    history_file = tmp_path / "eps_ttm_history_enriched.csv"
    reports_file = tmp_path / "reports.csv"
    overrides_file = tmp_path / "report_date_overrides.csv"
    cache_file = tmp_path / "eps_report_date_cache.csv"
    missing_file = tmp_path / "eps_report_date_missing.csv"
    applied_file = tmp_path / "eps_report_date_overrides_applied.csv"

    pd.DataFrame(
        columns=["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    ).to_csv(history_file, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "ALIV-SDB.ST",
                "report_period": "2019-Q2",
                "effective_date": "",
                "eps_ttm": 26.0406,
            }
        ]
    ).to_csv(reports_file, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "ALIV-SDB.ST",
                "report_period": "2019-Q2",
                "report_date": "2019-07-19",
                "source": "Autoliv official archive",
            }
        ]
    ).to_csv(overrides_file, index=False)

    apply_overrides(
        history_file=history_file,
        reports_file=reports_file,
        overrides_file=overrides_file,
        cache_file=cache_file,
        missing_file=missing_file,
        applied_file=applied_file,
    )

    cache = pd.read_csv(cache_file)
    assert cache.to_dict("records") == [
        {
            "ticker": "ALIV-SDB.ST",
            "report_period": "2019-Q2",
            "report_date": "2019-07-19",
        }
    ]


def test_override_matches_yahoo_period_by_calendar_quarter(tmp_path: Path):
    history_file = tmp_path / "eps_ttm_history_enriched.csv"
    reports_file = tmp_path / "reports.csv"
    overrides_file = tmp_path / "report_date_overrides.csv"
    cache_file = tmp_path / "eps_report_date_cache.csv"
    missing_file = tmp_path / "eps_report_date_missing.csv"
    applied_file = tmp_path / "eps_report_date_overrides_applied.csv"

    pd.DataFrame(
        columns=["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    ).to_csv(history_file, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "CLAS-B.ST",
                "period_end": "2026-07-31",
                "report_period": "YAHOO-2026-07-31",
                "effective_date": "2026-09-02",
                "eps_ttm": 19.75,
            }
        ]
    ).to_csv(reports_file, index=False)
    pd.DataFrame(
        [
            {
                "ticker": "CLAS-B.ST",
                "report_period": "2026-Q3",
                "report_date": "2026-09-03",
                "source": "Clas Ohlson official reports archive",
            }
        ]
    ).to_csv(overrides_file, index=False)

    apply_overrides(
        history_file=history_file,
        reports_file=reports_file,
        overrides_file=overrides_file,
        cache_file=cache_file,
        missing_file=missing_file,
        applied_file=applied_file,
    )

    reports = pd.read_csv(reports_file, dtype=str)
    assert reports.loc[0, "report_period"] == "YAHOO-2026-07-31"
    assert reports.loc[0, "effective_date"] == "2026-09-03"
