"""Equal stock allocations for Method's all-stock view, without mixing concurrent trades."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .index_benchmark import INDEX_FILE
from .method_metrics import equity_metrics, hold_curve, trade_metrics
from .utils import read_json, write_json_atomic

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


def build_aggregate(stocks: dict, backtests: dict, generated_at: str = "", index_candles: list[dict] | None = None) -> dict:
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
        dates = sorted({c["date"] for s in ready.values() for c in s["candles"] if start <= c["date"] <= end})
        summaries = {}
        benchmarks = []
        hold_equity = np.zeros(len(dates))
        for ticker, stock in ready.items():
            curve, trade = hold_curve(stock["candles"], backtests[ticker].get("_dividends", []), dates)
            hold_equity += curve / len(ready)
            if trade:
                benchmarks.append(dict(trade, ticker=ticker))
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
            prelim = [t["current_return_pct"] for t in opens if t.get("current_return_pct") is not None]
            summaries[strategy] = {**equity_metrics(equity), **trade_metrics(closed),
                "open_count": len(opens), "open_return_pct": float(np.mean(prelim)) if prelim else None}
        summaries["buy_and_hold"] = {**equity_metrics(hold_equity), **trade_metrics(benchmarks), "open_count": 0, "open_return_pct": None}
        # Use the actual index observation window, never pretend a stale quote is today's.
        index_window = [c for c in (index_candles or []) if dates[0] <= c["date"] <= dates[-1]]
        index_dates = [d for d in dates if index_window and index_window[0]["date"] <= d <= index_window[-1]["date"]]
        if len(index_window) >= 2:
            curve, trade = hold_curve(index_window, [], index_dates, commission=0)
            summaries["omxsgi"] = {**equity_metrics(curve), **trade_metrics([trade]), "open_count": 0, "open_return_pct": None,
                                    "start_date": trade["entry_date"], "end_date": trade["exit_date"]}
            index_trades = [dict(trade, ticker="OMXSGI")]
        else:
            summaries["omxsgi"] = {**equity_metrics(np.array([])), **trade_metrics([]), "open_count": 0, "open_return_pct": None}
            index_trades = []
        result["periods"][period] = {"start_date": start, "end_date": end, "strategies": summaries,
                                   "reference_trades": {"buy_and_hold": benchmarks, "omxsgi": index_trades},
                                   "benchmark_pct": summaries["buy_and_hold"]["return_pct"], "benchmark_count": len(benchmarks)}
    return result


def write_aggregate(stocks: dict, generated_at: str, directory: Path | None = None) -> dict:
    directory = directory or ROOT / "docs" / "data" / "backtests"
    variants = {ticker: json.loads((directory / f"{ticker}.json").read_text()) for ticker in stocks if (directory / f"{ticker}.json").exists()}
    payload = build_aggregate(stocks, variants, generated_at, read_json(INDEX_FILE, default={}).get("candles", []))
    write_json_atomic(directory / "all.json", payload)
    return payload


if __name__ == "__main__":
    dashboard = json.loads((ROOT / "docs" / "data" / "dashboard.json").read_text())
    payload = write_aggregate(dashboard["stocks"], dashboard["meta"]["generated_at"])
    print(f"Built Method aggregate for {payload['meta']['stock_count']} stocks.")
