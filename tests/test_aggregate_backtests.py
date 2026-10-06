"""Synthetic examples: allocations, simultaneous trades and period exclusions."""
import pytest
import numpy as np

from src.aggregate_backtests import STRATEGIES, build_aggregate


def dataset(returns):
    stocks = {}
    variants = {}
    for ticker, value in returns.items():
        stocks[ticker] = {"candles": [{"date": "2025-10-05", "close": 100}, {"date": "2026-10-05", "close": 100 * (1 + value / 100)}]}
        trade = {"entry_date": "2025-10-05", "exit_date": "2026-10-05", "entry_price": 100, "exit_price": 100 * (1 + value / 100), "return_pct": value}
        variants[ticker] = {key: {"closed_trades": [trade.copy()], "open_lots": [], "end_date": "2026-10-05"} for key in STRATEGIES}
    return stocks, variants


def test_concurrent_stock_trades_have_equal_allocations_not_compounding():
    stocks, variants = dataset({"EXAMPLE-A": 10, "EXAMPLE-B": 20})
    result = build_aggregate(stocks, variants)
    summary = result["periods"]["1"]["strategies"]["standard"]
    assert summary["return_pct"] == pytest.approx(15)
    assert summary["trade_count"] == 2
    assert summary["win_rate_pct"] == 100
    assert result["meta"]["stock_count"] == 2


def test_no_closed_trades_preserves_idle_allocation_and_open_is_separate():
    stocks, variants = dataset({"EXAMPLE-A": 10, "EXAMPLE-B": 0})
    for key in STRATEGIES:
        variants["EXAMPLE-B"][key]["closed_trades"] = []
        variants["EXAMPLE-B"][key]["open_lots"] = [{"entry_date": "2026-01-01", "current_return_pct": -50}]
    result = build_aggregate(stocks, variants)
    summary = result["periods"]["1"]["strategies"]["standard"]
    assert summary["return_pct"] == pytest.approx(5)
    assert summary["open_count"] == 1
    assert summary["open_return_pct"] == -50


def test_old_entries_excluded_using_common_period_for_every_stock():
    stocks, variants = dataset({"EXAMPLE-A": 10, "EXAMPLE-B": 20})
    for key in STRATEGIES:
        variants["EXAMPLE-A"][key]["closed_trades"][0]["entry_date"] = "2025-10-04"
    result = build_aggregate(stocks, variants)
    assert result["periods"]["1"]["start_date"] == "2025-10-05"
    assert result["periods"]["1"]["strategies"]["standard"]["return_pct"] == pytest.approx(10)
    assert result["periods"]["1"]["strategies"]["standard"]["trade_count"] == 1


def test_drawdown_uses_combined_equity_not_average_stock_drawdowns():
    stocks, variants = dataset({"EXAMPLE-A": 20, "EXAMPLE-B": -20})
    summary = build_aggregate(stocks, variants)["periods"]["1"]["strategies"]["standard"]
    assert summary["return_pct"] == pytest.approx(0)
    assert summary["max_drawdown_pct"] > -1  # equal opposite moves cancel, apart from entry commission


def test_incomplete_data_is_reported_instead_of_silently_weighted():
    stocks, variants = dataset({"EXAMPLE-A": 10, "EXAMPLE-B": 20})
    del variants["EXAMPLE-B"]
    result = build_aggregate(stocks, variants)
    assert result["meta"]["excluded_stocks"] == ["EXAMPLE-B"]
    assert result["meta"]["stock_count"] == 1


def test_buy_and_hold_portfolio_weights_cash_and_concurrent_shares_equally():
    stocks, variants = dataset({"EXAMPLE-A": 10, "EXAMPLE-B": 20})
    result = build_aggregate(stocks, variants)["periods"]["1"]
    summary = result["strategies"]["buy_and_hold"]
    assert summary["return_pct"] == pytest.approx((115*.9975/100.25-1)*100)
    assert summary["trade_count"] == 2
    assert len(result["reference_trades"]["buy_and_hold"]) == 2
    stocks["EXAMPLE-B"]["candles"] = stocks["EXAMPLE-B"]["candles"][-1:]
    result = build_aggregate(stocks, variants)["periods"]["1"]
    assert result["strategies"]["buy_and_hold"]["return_pct"] == pytest.approx(((110*.9975/100.25-1)*100)/2)
    assert result["strategies"]["buy_and_hold"]["trade_count"] == 1


def test_sharpe_is_computed_on_the_combined_daily_capital_curve():
    stocks, variants = dataset({"EXAMPLE-A": 20, "EXAMPLE-B": -20})
    summary = build_aggregate(stocks, variants)["periods"]["1"]["strategies"]["standard"]
    changes = np.array([1/1.0025 - 1, 1.0025 - 1])
    assert summary["sharpe_ratio"] == pytest.approx(changes.mean()/changes.std(ddof=1)*np.sqrt(252))


def test_index_uses_selected_window_actual_last_date_and_no_commission():
    stocks, variants = dataset({"EXAMPLE-A": 10})
    points = [{"date":"2025-10-04","close":1}, {"date":"2025-10-05","close":100},
              {"date":"2026-10-04","close":110}, {"date":"2026-10-06","close":900}]
    # Only observations coinciding with stock trading sessions can enter its daily curve.
    stocks["EXAMPLE-A"]["candles"].insert(1,{"date":"2026-10-04","close":110})
    period = build_aggregate(stocks,variants,index_candles=points)["periods"]["1"]
    summary = period["strategies"]["omxsgi"]
    assert summary["return_pct"] == pytest.approx(10)
    assert summary["end_date"] == "2026-10-04"
    assert period["reference_trades"]["omxsgi"][0]["exit_date"] == "2026-10-04"


def test_missing_index_data_has_no_invented_return_or_sharpe():
    stocks, variants = dataset({"EXAMPLE-A": 10})
    summary = build_aggregate(stocks,variants)["periods"]["1"]["strategies"]["omxsgi"]
    assert summary["return_pct"] is None
    assert summary["sharpe_ratio"] is None
    assert summary["trade_count"] == 0
