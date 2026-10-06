"""Synthetic cases for independent filters and report session boundaries."""
import pandas as pd
import pytest

from src.strategy import run_strategy
from src.strategy_backtests import report_filters, build_strategy_backtests


def frame(dates, scores, ma=100):
    return pd.DataFrame({"Date": pd.to_datetime(dates), "Open": 100., "Close": 100.,
                         "Score": scores, "MA200": ma, "FundamentalLock": False})


def test_ten_sessions_blocks_and_eleven_sessions_allows_execution():
    # Easter includes Good Friday and Easter Monday, both closed in Stockholm.
    data = frame(pd.bdate_range("2026-03-16", "2026-04-08"), [0.] * 18)
    filtered = report_filters(data, [pd.Timestamp("2026-04-08")])
    by_date = filtered.set_index("Date")
    assert by_date.loc["2026-03-20", "BuyExecutionAllowed"]  # 11 sessions
    assert not by_date.loc["2026-03-23", "BuyExecutionAllowed"]  # 10 sessions
    assert not by_date.loc["2026-03-20", "BuyAllowed"]  # next opening is blocked
    assert by_date.loc["2026-04-07", "ForceReportExit"]
    assert not by_date.loc["2026-04-08", "BuyExecutionAllowed"]


def test_report_exit_overrides_fundamental_lock_and_score():
    data = frame(pd.bdate_range("2026-01-05", periods=5), [0, 50, 50, 50, 50])
    data["BuyAllowed"] = [True, True, False, False, False]
    data["BuyExecutionAllowed"] = True
    data["ForceReportExit"] = [False, False, False, True, False]
    data.loc[3:, "FundamentalLock"] = True
    result = run_strategy(data, "SYNTHETIC.ST")
    assert len(result["trades"]) == 1
    assert result["trades"][0]["exit_date"] == "2026-01-08"
    assert result["trades"][0]["exit_reason"] == "report"
    assert not result["open_lots"]


def test_missing_report_dates_blocks_buys():
    data = frame(pd.bdate_range("2026-01-05", periods=5), [0] * 5)
    result = run_strategy(report_filters(data, []), "SYNTHETIC.ST")
    assert not result["open_lots"]
    assert not result["trades"]


def test_ma200_is_strict_and_does_not_filter_sales(monkeypatch):
    import src.strategy_backtests as backtests
    monkeypatch.setattr(backtests, "automatic_calendar", lambda: pd.DataFrame())
    data = frame(pd.bdate_range("2026-01-05", periods=6), [0, 0, 50, 100, 50, 50])
    data["Close"] = [100, 101, 99, 99, 99, 99]
    data.loc[2, "Open"] = 101
    standard = run_strategy(data, "SYNTHETIC.ST")
    variants = build_strategy_backtests(data, "SYNTHETIC.ST", pd.DataFrame(columns=["ticker"]), pd.DataFrame(), standard)
    assert variants["standard"]["closed_trades"] == standard["trades"]
    trade = variants["ma200"]["closed_trades"][0]
    assert trade["entry_date"] == "2026-01-07"  # equal MA blocks the earlier entry
    assert trade["exit_date"] == "2026-01-09"  # below MA still sells
    assert trade["return_pct"] == pytest.approx((100 * .9975 / (101 * 1.0025) - 1) * 100)


def test_report_day_blocks_but_following_day_can_buy():
    data = frame(pd.bdate_range("2026-01-05", periods=6), [0] * 6)
    filtered = report_filters(data, [pd.Timestamp("2026-01-07"), pd.Timestamp("2026-04-07")])
    assert not filtered.iloc[2]["BuyAllowed"]
    assert filtered.iloc[3]["BuyAllowed"]
    result = run_strategy(filtered, "SYNTHETIC.ST")
    assert result["open_lots"][0]["entry_date"] == "2026-01-09"


def test_ma200_blocks_opening_gap_below_last_completed_average(monkeypatch):
    import src.strategy_backtests as backtests
    monkeypatch.setattr(backtests, "automatic_calendar", lambda: pd.DataFrame())
    data = frame(pd.bdate_range("2026-01-05", periods=3), [0, 50, 50])
    data["Close"] = 101
    data["Open"] = [101, 99, 101]
    variants = build_strategy_backtests(data, "SYNTHETIC.ST", pd.DataFrame(columns=["ticker"]), pd.DataFrame(), run_strategy(data, "SYNTHETIC.ST"))
    assert len(variants["standard"]["open_lots"]) == 1
    assert not variants["ma200"]["open_lots"]
