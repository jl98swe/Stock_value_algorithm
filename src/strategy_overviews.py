"""Compact current positions and recent executions for the four own strategies."""
from pathlib import Path

from .utils import write_json_atomic

STRATEGIES = ("standard", "standard_stop_loss_10", "standard_two_positions", "ma200", "report_avoidance")


def write_strategy_overviews(stocks: dict, meta: dict, path: Path) -> dict:
    dates = sorted({c["date"] for stock in stocks.values() for c in stock.get("candles", [])})[-20:]
    execution_dates = [s["execution_date"] for stock in stocks.values()
                       for view in stock.get("strategies", {}).values()
                       for s in view.get("signals", []) if s.get("execution_date")]
    payload = {"meta": {**meta, "trading_dates": dates,
                        "latest_execution_date": max(dates + execution_dates, default=None)}, "strategies": {}}
    for key in STRATEGIES:
        views = {}
        for ticker, stock in stocks.items():
            live = stock["strategies"][key]
            views[ticker] = {"latest": stock["latest"], "active_for_updates": stock.get("active_for_updates", True), **live}
        payload["strategies"][key] = {"stocks": views}
    write_json_atomic(path, payload)
    return payload
