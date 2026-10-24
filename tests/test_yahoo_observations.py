"""Synthetic examples: archive data independently of model selection."""
import json
import pandas as pd

from src.yahoo_observations import archive_eps


def test_baseline_keeps_available_yahoo_history_once(tmp_path):
    from src.yahoo_observations import seed_history
    path = tmp_path / "data/earnings/quarterly_eps.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame([{"source": "Yahoo Finance", "eps": 2}, {"source": "Manual", "eps": 3}]).to_csv(path, index=False)
    seed_history(tmp_path)
    seed_history(tmp_path)
    lines = (path.parent / "yahoo_observations/baseline_quarterly_eps.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["records"] == [{"source": "Yahoo Finance", "eps": 2}]


def test_every_fetch_and_same_day_revisions_are_retained(tmp_path):
    frame = pd.DataFrame([{"ticker": "TEST.ST", "eps_ttm": 1.23, "eps_currency": "USD",
                           "period_end": pd.Timestamp("2026-06-30"), "source": "Yahoo"}])
    archive_eps(frame, "ttm", tmp_path)
    frame.loc[0, "eps_ttm"] = 1.24
    archive_eps(frame, "ttm", tmp_path)
    archive_eps(frame, "ttm", tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "ttm.jsonl").read_text().splitlines()]
    assert [r["records"][0]["eps_ttm"] for r in rows] == [1.23, 1.24, 1.24]
    assert all(r["fetched_at"] and r["records"][0]["eps_currency"] == "USD" for r in rows)


def test_archive_does_not_round_fetched_float(tmp_path):
    value = 0.12345678901234567
    archive_eps(pd.DataFrame([{"eps": value}]), "precision", tmp_path)
    assert json.loads((tmp_path / "precision.jsonl").read_text())["records"][0]["eps"] == value


def test_all_returned_ttm_periods_archived_including_unknown_currency(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import src.earnings as e
    import src.yahoo_observations as archive
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)
    values = [{"asOfDate": "2026-06-30", "currencyCode": "SEK", "reportedValue": {"raw": 2.0}},
              {"asOfDate": "2026-09-30", "reportedValue": {"raw": 3.0}}]
    payload = {"timeseries": {"result": [{e.EPS_METRIC: values}]}}
    client = SimpleNamespace(cache_get=lambda **kwargs: SimpleNamespace(text=json.dumps(payload)))
    monkeypatch.setattr(e.yf, "Ticker", lambda *args: SimpleNamespace(_data=client))
    selected = e._fetch_eps_one("TEST.ST", "2026-10-24")
    assert selected["eps_ttm"] == 2.0
    records = json.loads((tmp_path / "trailingDilutedEPS_periods.jsonl").read_text())["records"]
    assert [r["eps_ttm"] for r in records] == [2.0, 3.0]
    assert records[1]["eps_currency"] == ""


def test_quarterly_archive_precedes_existing_period_filter_and_keeps_manual_priority(tmp_path, monkeypatch):
    import src.quarterly_eps as q
    import src.yahoo_observations as archive
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)
    row = {"ticker": "TEST.ST", "period_end": "2025-06-30", "observed_date": "2026-10-23",
           "report_date": "2025-07-15", "eps_currency": "SEK", "source": q.DILUTED_SOURCE,
           "metric": q.DILUTED_METRIC, "eps": 1.0}
    existing = q._normalise(pd.DataFrame([row, {**row, "metric": q.MANUAL_METRIC, "eps": 3.0, "source": "Manual"}]))
    monkeypatch.setattr(q, "_ticker_universe", lambda: ["TEST.ST"])
    monkeypatch.setattr(q, "load_quarterly_eps", lambda: existing)
    monkeypatch.setattr(q, "_fetch_recent_one", lambda *args: [{**row, "eps": 2.0}])
    monkeypatch.setattr(q, "_publish_json", lambda *args: None)
    result = q.update_recent(tickers=["TEST.ST"])
    records = json.loads((tmp_path / "quarterlyDilutedEPS.jsonl").read_text())["records"]
    assert records[0]["eps"] == 2.0
    assert result.equals(existing)
    assert q.find_prior_year_eps("TEST.ST", "2026-06-30", result)["eps"] == 3.0
