from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.validate_outputs import _validate_historical_eps_dates


def _write_history(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _row(period: str, report_date: str, eps: float = 1.0) -> dict[str, object]:
    return {
        "ticker": "TEST.ST",
        "report_period": period,
        "report_date": report_date,
        "eps_ttm": eps,
        "currency": "SEK",
    }


def test_historical_eps_dates_allow_broken_fiscal_year_and_skipped_quarter(
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.csv"
    _write_history(
        path,
        [
            _row("2023-Q3", "2023-08-24"),
            _row("2023-Q4", "2023-11-30"),
            _row("2024-Q2", "2024-06-05"),
        ],
    )

    _validate_historical_eps_dates(path)


def test_historical_eps_dates_reject_stale_fiscal_label_alignment(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    _write_history(path, [_row("2023-Q3", "2023-03-09")])

    with pytest.raises(ValueError, match="orimligt långt före kalenderkvartalet"):
        _validate_historical_eps_dates(path)


def test_historical_eps_dates_reject_large_gap_between_consecutive_quarters(
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.csv"
    _write_history(
        path,
        [
            _row("2023-Q2", "2023-04-29"),
            _row("2023-Q3", "2023-09-30"),
        ],
    )

    with pytest.raises(ValueError, match="orimlig lucka"):
        _validate_historical_eps_dates(path)
