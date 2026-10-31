"""Synthetic examples: correcting EPS must invalidate scores and trading output."""
import pandas as pd
import pytest

from src.fundamentals import normalise_reports
from src.report_date_revisions import (
    changed_eps_cutoffs, score_snapshot, save_score_dates, load_score_dates,
    log_score_date_revisions,
)
from src.score_history import apply_frozen_scores
from src.strategy import run_strategy


def reports(value=2.0, currency="SEK", source="Manual report", verified=True):
    return normalise_reports(pd.DataFrame([dict(
        ticker="EXAMPLE.ST", report_period="2026-Q3", period_end="2026-09-30",
        effective_date="2026-10-20", eps_ttm=value, verified=verified,
        source=source, notes="report_currency=" + currency)]))


@pytest.mark.parametrize("current", [reports(3), reports(currency="EUR"), reports(verified=False)])
def test_eps_currency_and_verification_changes_invalidate_same_date(current):
    old = score_snapshot(reports())
    assert changed_eps_cutoffs(current, old) == {"EXAMPLE.ST": pd.Timestamp("2026-10-20")}


def test_tv_correction_starts_at_model_period_end_and_keeps_other_tickers():
    old = reports(source="TradingView / diluted TTM")
    current = reports(3, source="TradingView / diluted TTM")
    assert changed_eps_cutoffs(current, score_snapshot(old)) == {"EXAMPLE.ST": pd.Timestamp("2026-09-30")}


def test_added_removed_and_retimed_report_uses_earliest_affected_model_date():
    old = score_snapshot(reports(source="TradingView / diluted TTM"))
    assert changed_eps_cutoffs(reports().iloc[:0], old) == {"EXAMPLE.ST": pd.Timestamp("2026-09-30")}
    new = reports(3, source="TradingView / diluted TTM")
    new["period_end"] = pd.Timestamp("2026-09-29")
    assert changed_eps_cutoffs(new, old) == {"EXAMPLE.ST": pd.Timestamp("2026-09-29")}


def test_successful_snapshot_roundtrip_is_idempotent_and_description_does_not_rebase(tmp_path):
    path = tmp_path / "snapshot.csv"
    current = reports(2.123456789012345)
    save_score_dates(current, path)
    previous = load_score_dates(path)
    assert changed_eps_cutoffs(current, previous) == {}
    current["source"] = "Revised source description"
    current["verified_at"] = pd.Timestamp("2026-10-31", tz="UTC")
    assert changed_eps_cutoffs(current, previous) == {}


def test_legacy_snapshot_can_be_loaded_without_rebuilding_unknown_history():
    old = score_snapshot(reports()).drop(columns=["eps_ttm", "eps_currency", "valuation_date", "calculation_mode"])
    assert changed_eps_cutoffs(reports(3), old) == {}


def test_revision_audit_records_eps_and_currency_even_without_date_change(tmp_path):
    path = tmp_path / "audit.csv"
    old = score_snapshot(reports())
    current = reports(3, currency="EUR")
    log_score_date_revisions(current, old, "synthetic-build", path)
    row = pd.read_csv(path).iloc[0]
    assert (row.eps_ttm_old, row.eps_ttm_new) == (2, 3)
    assert (row.eps_currency_old, row.eps_currency_new) == ("SEK", "EUR")
    assert row.effective_date_old == row.effective_date_new


def test_correction_replaces_frozen_scores_and_rebuilds_buy_and_trade():
    old = score_snapshot(reports())
    cutoff = changed_eps_cutoffs(reports(3), old)["EXAMPLE.ST"]
    dates = pd.to_datetime(["2026-10-19", "2026-10-20", "2026-10-21"])
    history = pd.DataFrame({"ticker": ["EXAMPLE.ST"] * 3, "date": dates, "score": [50, 50, 50]})
    valued = pd.DataFrame({"Date": dates, "Open": [100.] * 3, "Close": [100.] * 3,
                          "Score": [99., .5, 50.], "FundamentalLock": [False] * 3,
                          "LockReason": [""] * 3})
    unchanged, _ = apply_frozen_scores(valued, "EXAMPLE.ST", history, frozen_at="old")
    corrected, _ = apply_frozen_scores(valued, "EXAMPLE.ST", history,
                                      frozen_at="new", recalculate_from=cutoff)
    assert corrected.Score.tolist() == [50, .5, 50]
    assert run_strategy(unchanged, "EXAMPLE.ST")["signals"] == []
    buys = [s for s in run_strategy(corrected, "EXAMPLE.ST")["signals"]
            if s["side"] == "BUY" and s["status"] == "executed"]
    assert len(buys) == 1
    assert buys[0]["signal_date"] == "2026-10-20"
    assert buys[0]["execution_date"] == "2026-10-21"
