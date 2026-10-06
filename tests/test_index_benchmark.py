import io

import pandas as pd
import pytest

from src import index_benchmark as module
from src.utils import write_json_atomic


def test_parser_filters_missing_bad_future_and_non_stockholm_session_quotes():
    data = "observation_date,NASDAQOMXSGI\n2019-08-30,100\n2026-01-01,100\n2026-01-02,110\n2026-01-05,\n2026-01-06,120\n2026-01-07,0\n2026-01-08,125\n"
    assert module.parse_index_csv(data,"2026-01-07") == [{"date":"2026-01-02","close":110}]
    with pytest.raises(ValueError):
        module.parse_index_csv("date,price\n2026-01-02,110", "2026-01-07")


def test_failed_update_keeps_last_successful_export(tmp_path, monkeypatch):
    path = tmp_path / "omxsgi.json"
    old = {"candles":[{"date":"2026-01-02","close":100}]}
    write_json_atomic(path, old)
    monkeypatch.setattr(module,"urlopen",lambda *a,**k: (_ for _ in ()).throw(OSError("offline")))
    assert module.update_index(path) == old
    with pytest.raises(OSError):
        module.update_index(tmp_path / "missing.json")


def test_update_retains_history_and_applies_revisions_without_partial_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "omxsgi.json"
    write_json_atomic(path, {"candles":[{"date":"2026-01-02","close":100},{"date":"2026-01-05","close":101}]})
    monkeypatch.setattr(module,"last_completed_session",lambda: pd.Timestamp("2026-01-07"))
    monkeypatch.setattr(module,"urlopen",lambda *a,**k: io.BytesIO(b"observation_date,NASDAQOMXSGI\n2026-01-05,102\n2026-01-07,110\n"))
    updated = module.update_index(path)
    assert updated["candles"] == [{"date":"2026-01-02","close":100},{"date":"2026-01-05","close":102},{"date":"2026-01-07","close":110}]
    monkeypatch.setattr(module,"urlopen",lambda *a,**k: io.BytesIO(b"observation_date,NASDAQOMXSGI\n2026-01-02,99\n"))
    assert module.update_index(path) == updated
