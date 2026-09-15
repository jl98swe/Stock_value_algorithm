"""Synthetic price examples: incomplete daily bars never enter the strategy."""
from pathlib import Path

import pandas as pd
import pytest

from src import fetch_data


@pytest.mark.parametrize("now,expected", [
    ("2026-09-15T11:00:00Z", "2026-09-14"),
    ("2026-09-15T15:29:59Z", "2026-09-14"),
    ("2026-09-15T15:30:00Z", "2026-09-15"),
    ("2026-09-13T19:00:00Z", "2026-09-11"),
    ("2026-01-07T16:29:59Z", "2026-01-05"),
    ("2026-01-07T16:30:00Z", "2026-01-07"),
    ("2026-04-02T10:59:59Z", "2026-04-01"),
    ("2026-04-02T11:00:00Z", "2026-04-02"),
    ("2026-04-06T18:00:00Z", "2026-04-02"),
])
def test_cutoff_uses_actual_stockholm_close(now, expected):
    assert fetch_data.last_completed_session(now) == pd.Timestamp(expected)


def _prices(days):
    return pd.DataFrame({
        "date": pd.to_datetime(days), "ticker": "EXAMPLE.ST",
        "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100,
    })


def test_offline_rebuild_excludes_cached_intraday_bar(tmp_path: Path):
    base = tmp_path / "base.parquet"
    updates = tmp_path / "updates.csv"
    _prices(["2026-09-11"]).to_parquet(base)
    _prices(["2026-09-14", "2026-09-15"]).to_csv(updates, index=False)
    actual = fetch_data.load_price_history(base, updates, as_of="2026-09-15T11:00:00Z")
    assert actual.date.dt.strftime("%Y-%m-%d").tolist() == ["2026-09-11", "2026-09-14"]


def test_download_and_saved_updates_exclude_intraday_even_if_yahoo_returns_it(tmp_path, monkeypatch):
    base = tmp_path / "base.parquet"
    updates = tmp_path / "updates.csv"
    _prices(["2026-09-11"]).to_parquet(base)
    _prices(["2026-09-14", "2026-09-15"]).to_csv(updates, index=False)
    requested = []

    def download(tickers, *, start, end):
        requested.append(end)
        return _prices(["2026-09-14", "2026-09-15"])

    monkeypatch.setattr(fetch_data, "_download", download)
    actual = fetch_data.update_prices(base, updates, as_of="2026-09-15T11:00:00Z")
    assert requested == ["2026-09-15"]
    assert actual.date.max() == pd.Timestamp("2026-09-14")
    assert pd.read_csv(updates).date.tolist() == ["2026-09-14"]
