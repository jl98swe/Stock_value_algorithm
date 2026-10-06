"""Equal stock allocations for Method's all-stock view, without mixing concurrent trades."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .utils import write_json_atomic

STRATEGIES = ("standard", "ma200", "report_avoidance")


def closed_equity(candles: list[dict], trades: list[dict], dividends: list[dict], dates: list[str]) -> np.ndarray:
    """Reinvest within each stock; exclude positions outside the requested window."""
    factors = {}
    cash = 1.0
    by_day = {c["date"]: c for c in candles}
    dividend_map = {}
    for item in dividends:
        dividend_map[item["date"]] = dividend_map.get(item["date"], 0) + float(item["amount"] or 0)
    for trade in sorted(trades, key=lambda t: t["entry_date"]):
        paid = 0.0
        for day, candle in by_day.items():
            if not trade["entry_date"] <= day <= trade["exit_date"]:
                continue
            if day > trade["entry_date"]:
                paid += dividend_map.get(day, 0.0)
            factor = (1 + trade["return_pct"] / 100 if day == trade["exit_date"] else
                      (candle["close"] + paid) / (trade["entry_price"] * 1.0025))
            factors[day] = cash * factor
        cash *= 1 + trade["return_pct"] / 100
        factors[trade["exit_date"]] = cash
    values = []
    current = 1.0
    for day in dates:
        current = factors.get(day, current)
        values.append(current)
    return np.asarray(values)


def build_aggregate(stocks: dict, backtests: dict, generated_at: str = "") -> dict:
    ready = {ticker: stock for ticker, stock in stocks.items() if stock.get("candles") and
             ticker in backtests and all(k in backtests[ticker] for k in STRATEGIES)}
    if not ready:
        return {"meta": {"stock_count": 0}, "periods": {}}
    end = max(s["candles"][-1]["date"] for s in ready.values())
    first = min(s["candles"][0]["date"] for s in ready.values())
    result = {"meta": {"generated_at": generated_at, "stock_count": len(ready),
                       "excluded_stocks": sorted(set(stocks) - set(ready)), "start_date": first, "end_date": end,
                       "weighting": "equal_stock_allocations"}, "periods": {}}
    for strategy in STRATEGIES:
        result[strategy] = {"closed_trades": [], "open_lots": [], "report_dates_count": 0}
        for ticker in ready:
            variant = backtests[ticker][strategy]
            result[strategy]["closed_trades"].extend(dict(t, ticker=ticker) for t in variant.get("closed_trades", []))
            result[strategy]["open_lots"].extend(dict(t, ticker=ticker, valuation_date=variant["end_date"]) for t in variant.get("open_lots", []))
            result[strategy]["report_dates_count"] += variant.get("report_dates_count", 0)
    for period in ("all", "1", "3", "5"):
        start = first if period == "all" else (pd.Timestamp(end) - pd.DateOffset(years=int(period))).date().isoformat()
        dates = sorted({start, end} | {c["date"] for s in ready.values() for c in s["candles"] if start <= c["date"] <= end})
        summaries = {}
        benchmarks = []
        for ticker, stock in ready.items():
            window = [c for c in stock["candles"] if start <= c["date"] <= end]
            if len(window) >= 2:
                dividends = sum(float(d["amount"] or 0) for d in backtests[ticker].get("_dividends", []) if window[0]["date"] < d["date"] <= window[-1]["date"])
                benchmarks.append(((window[-1]["close"] * .9975 + dividends) / (window[0]["close"] * 1.0025) - 1) * 100)
        for strategy in STRATEGIES:
            equity = np.zeros(len(dates))
            closed = []
            opens = []
            for ticker, stock in ready.items():
                variant = backtests[ticker][strategy]
                trades = [t for t in variant.get("closed_trades", []) if start <= t["entry_date"] <= t["exit_date"] <= end]
                closed.extend(trades)
                opens.extend(t for t in variant.get("open_lots", []) if start <= t["entry_date"] <= end)
                equity += closed_equity(stock["candles"], trades, backtests[ticker].get("_dividends", []), dates) / len(ready)
            returns = [t["return_pct"] for t in closed]
            prelim = [t["current_return_pct"] for t in opens if t.get("current_return_pct") is not None]
            summaries[strategy] = {"return_pct": float((equity[-1] - 1) * 100),
                "max_drawdown_pct": float(np.min((equity / np.maximum.accumulate(equity) - 1) * 100)),
                "trade_count": len(closed), "win_rate_pct": sum(r > 0 for r in returns) / len(returns) * 100 if returns else None,
                "average_trade_pct": float(np.mean(returns)) if returns else None,
                "open_count": len(opens), "open_return_pct": float(np.mean(prelim)) if prelim else None}
        result["periods"][period] = {"start_date": start, "end_date": end, "strategies": summaries,
                                   "benchmark_pct": float(np.mean(benchmarks)) if benchmarks else None,
                                   "benchmark_count": len(benchmarks)}
    return result


def write_aggregate(stocks: dict, generated_at: str, directory: Path | None = None) -> dict:
    directory = directory or ROOT / "docs" / "data" / "backtests"
    variants = {ticker: json.loads((directory / f"{ticker}.json").read_text()) for ticker in stocks if (directory / f"{ticker}.json").exists()}
    payload = build_aggregate(stocks, variants, generated_at)
    write_json_atomic(directory / "all.json", payload)
    return payload


if __name__ == "__main__":
    dashboard = json.loads((ROOT / "docs" / "data" / "dashboard.json").read_text())
    payload = write_aggregate(dashboard["stocks"], dashboard["meta"]["generated_at"])
    print(f"Built Method aggregate for {payload['meta']['stock_count']} stocks.")
