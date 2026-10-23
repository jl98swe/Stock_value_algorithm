"""Synthetic examples: opening execution and EOD reconciliation."""
import numpy as np
import pandas as pd
import pytest

from src.opening_sessions import append_opening, ingest, opening_fingerprint, export_pending
from src.strategy import run_strategy
from src.strategy_backtests import build_strategy_backtests


def frame(scores):
    dates = pd.bdate_range(end="2026-10-22", periods=len(scores))
    return pd.DataFrame({"Date": dates, "Open": 100., "High": 101., "Low": 99.,
                         "Close": 100., "MA200": 90., "Score": scores,
                         "FundamentalLock": False, "LockReason": ""})


def observation(price=102):
    return {"2026-10-23": {"TEST.ST": {"price": price}}}


@pytest.mark.parametrize("variant", ["standard", "ma200", "report_avoidance",
                                    "standard_stop_loss_10", "standard_two_positions"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_all_variants_execute_once_and_reconcile_at_close(variant, side, monkeypatch):
    import src.strategy_backtests as variants
    monkeypatch.setattr(variants, "automatic_calendar", lambda: pd.DataFrame())
    monkeypatch.setattr(variants, "_combined_schedule", lambda *args: pd.DataFrame({
        "ticker": ["TEST.ST"], "report_date_start": [pd.Timestamp("2027-01-28")]}))
    scores = [50.] * 15 + [.4] if side == "BUY" else [.4] + [50.] * 14 + [99.2]
    original = frame(scores)
    reports = pd.DataFrame(columns=["ticker", "published_at", "effective_date"])
    schedule = pd.DataFrame({"ticker": ["TEST.ST"], "report_date": [pd.Timestamp("2027-01-28")]})
    def result(data):
        return build_strategy_backtests(data, "TEST.ST", reports, schedule,
                                       run_strategy(data, "TEST.ST"))[variant]
    opening = append_opening(original, "TEST.ST", observation())
    assert np.isnan(opening.iloc[-1].Score)
    intraday = result(opening)
    assert result(append_opening(original, "TEST.ST", observation())) == intraday
    if side == "BUY":
        fills = [t for t in intraday["open_lots"] if t["entry_date"] == "2026-10-23"]
        assert len(fills) == 1
        assert fills[0]["entry_signal_date"] == "2026-10-22"
        assert fills[0]["entry_price"] == 102
    else:
        fills = [t for t in intraday["closed_trades"] if t["exit_date"] == "2026-10-23"]
        assert len(fills) == 1
        assert fills[0]["exit_signal_date"] == "2026-10-22"
        assert fills[0]["exit_price"] == 102
    eod = opening.copy()
    eod.loc[eod.index[-1], ["Close", "Low", "High", "Score"]] = [103, 101, 104, 50]
    assert len(append_opening(eod, "TEST.ST", observation())) == len(eod)
    closed = result(eod)
    assert len(closed["closed_trades"]) == len(intraday["closed_trades"])
    assert len(closed["open_lots"]) == len(intraday["open_lots"])


def test_no_guessing_across_missing_session_or_missing_open():
    original = frame([50, .4])
    assert append_opening(original, "TEST.ST", {}) is original
    assert append_opening(original, "TEST.ST", {"2026-10-26": observation()["2026-10-23"]}) is original


def test_opening_export_fingerprint_is_stable_until_new_input(tmp_path):
    path = tmp_path / "openings.json"
    assert opening_fingerprint(path) == ""
    path.write_text('{"2026-10-23":{}}')
    first = opening_fingerprint(path)
    assert first == opening_fingerprint(path)
    path.write_text('{"2026-10-26":{}}')
    assert opening_fingerprint(path) != first


def test_partial_publication_retries_until_chart_and_signals_match(tmp_path):
    import json
    openings = tmp_path / "openings.json"
    openings.write_text('{}')
    chart, signals = tmp_path / "chart.json", tmp_path / "signals.json"
    current = json.dumps({"meta": {"opening_sessions_sha256": opening_fingerprint(openings)}})
    chart.write_text(current)
    signals.write_text('{}')
    assert export_pending(openings, [chart, signals])
    signals.write_text(current)
    assert not export_pending(openings, [chart, signals])


def test_opening_ingest_rejects_late_wrong_currency_and_is_idempotent(tmp_path):
    path = tmp_path / "openings.json"
    quote = {"price": 102, "currency": "SEK", "source": "Avanza", "as_of": "2026-10-23T09:00:00+02:00"}
    cache = {"session_date": "2026-10-23", "stocks": {
        "TEST.ST": {"opening": quote},
        "LATE.ST": {"opening": {**quote, "as_of": "2026-10-23T13:00:00+02:00"}},
        "FX.ST": {"opening": {**quote, "currency": "EUR"}}}}
    now = "2026-10-23T14:00:00+02:00"
    assert ingest(cache, path, now=now) == 1
    cache["stocks"]["TEST.ST"]["opening"]["price"] = 999
    assert ingest(cache, path, now=now) == 0
    import json
    assert json.loads(path.read_text())["2026-10-23"]["TEST.ST"]["price"] == 102
    with pytest.raises(ValueError):
        ingest(cache, path, now="2026-10-24T14:00:00+02:00")


def test_opening_keeps_scheduled_report_and_yesterdays_exit(monkeypatch):
    import src.strategy_backtests as variants
    monkeypatch.setattr(variants, "automatic_calendar", lambda: pd.DataFrame())
    monkeypatch.setattr(variants, "_combined_schedule", lambda *args: pd.DataFrame({
        "ticker": ["TEST.ST", "TEST.ST"],
        "report_date_start": pd.to_datetime(["2026-10-23", "2027-01-28"])}))
    original = frame([.4] + [50.] * 29)
    reports = pd.DataFrame(columns=["ticker"])
    def result(data):
        return build_strategy_backtests(data, "TEST.ST", reports, pd.DataFrame(),
                                       run_strategy(data, "TEST.ST"))["report_avoidance"]
    before = result(original)
    assert before["closed_trades"][-1]["exit_date"] == "2026-10-22"
    after = result(append_opening(original, "TEST.ST", observation()))
    assert after["closed_trades"] == before["closed_trades"]
