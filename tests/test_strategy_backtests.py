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


def test_latest_report_filter_can_plan_a_buy_for_the_next_session():
    data = frame(pd.bdate_range("2026-01-05", periods=3), [50,50,0])
    filtered = report_filters(data,[pd.Timestamp("2026-04-07")])
    assert filtered.iloc[-1]["BuyAllowed"]
    result = run_strategy(filtered,"SYNTHETIC.ST")
    assert result["summary"]["pending_signal"]["side"] == "BUY"
    assert not result["open_lots"]


def test_latest_buy_block_checks_next_exchange_session_not_a_missing_price_row():
    data = frame(["2026-03-20"], [0])
    assert not report_filters(data,[pd.Timestamp("2026-04-08")]).iloc[-1]["BuyAllowed"]


def test_overviews_use_independent_positions_and_filters(monkeypatch):
    import src.strategy_backtests as backtests
    from src.pipeline import _strategy_live_payload
    monkeypatch.setattr(backtests,"automatic_calendar",lambda: pd.DataFrame())
    data = frame(pd.bdate_range("2026-01-05",periods=3),[0,50,50])
    data["Close"] = 99
    variants = build_strategy_backtests(data,"SYNTHETIC.ST",pd.DataFrame(columns=["ticker"]),pd.DataFrame(),
                                       run_strategy(data,"SYNTHETIC.ST"),_strategy_live_payload)
    assert variants["standard"]["overview"]["position"]["lots"] == 1
    assert variants["ma200"]["overview"]["position"]["lots"] == 0
    assert variants["report_avoidance"]["overview"]["position"]["lots"] == 0
    assert not variants["ma200"]["overview"]["strategy_filter"]["buy_allowed"]
    assert not variants["report_avoidance"]["overview"]["strategy_filter"]["buy_allowed"]


def test_report_overview_plans_forced_exit_even_with_neutral_score_and_lock(monkeypatch):
    import src.strategy_backtests as backtests
    from src.pipeline import _strategy_live_payload
    monkeypatch.setattr(backtests,"automatic_calendar",lambda: pd.DataFrame({"ticker":["SYNTHETIC.ST"],
        "report_date_start":pd.to_datetime(["2026-02-10"]),"report_date_end":pd.to_datetime(["2026-02-10"]),
        "source":["test"],"date_status":["confirmed"],"observed_date":pd.to_datetime(["2026-01-01"])}))
    data = frame(pd.bdate_range("2026-01-05","2026-02-06"),[0]+[50]*24)
    data.loc[data.index[-1],"FundamentalLock"] = True
    variants = build_strategy_backtests(data,"SYNTHETIC.ST",pd.DataFrame(columns=["ticker"]),pd.DataFrame(),
                                       run_strategy(data,"SYNTHETIC.ST"),_strategy_live_payload)
    live = variants["report_avoidance"]["overview"]
    assert live["position"]["lots"] == 1
    assert live["next_action"]["type"] == "SELL"
    assert live["next_action"]["exit_reason"] == "report"
    assert live["next_action"]["execute_on"] == "2026-02-09"
    assert not live["signals"]  # old buy lies outside the recent twenty sessions
