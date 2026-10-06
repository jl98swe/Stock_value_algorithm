"""Daily capital curves for the Method comparisons (cash dividends, no tax)."""
from __future__ import annotations

import numpy as np


def equity_metrics(equity: np.ndarray) -> dict:
    values = np.asarray(equity, dtype=float)
    if not len(values):
        return {"return_pct": None, "max_drawdown_pct": None, "sharpe_ratio": None}
    previous = np.r_[1.0, values[:-1]]
    returns = values / previous - 1
    deviation = np.std(returns, ddof=1) if len(returns) >= 2 else 0
    sharpe = float(np.mean(returns) / deviation * np.sqrt(252)) if deviation > 1e-12 else None
    peaks = np.maximum.accumulate(np.r_[1.0, values])[1:]
    return {"return_pct": float((values[-1] - 1) * 100),
            "max_drawdown_pct": float(np.min((values / peaks - 1) * 100)),
            "sharpe_ratio": sharpe}


def hold_curve(candles: list[dict], dividends: list[dict], dates: list[str],
               *, commission: float = .0025) -> tuple[np.ndarray, dict | None]:
    """Buy at the first close in the window, value daily, sell at the last close."""
    if not dates:
        return np.array([]), None
    window = sorted((c for c in candles if dates[0] <= c["date"] <= dates[-1]), key=lambda c: c["date"])
    if len(window) < 2:
        return np.ones(len(dates)), None
    first, last = window[0], window[-1]
    dividend_map = {}
    for item in dividends:
        if first["date"] < item["date"] <= last["date"]:
            dividend_map[item["date"]] = dividend_map.get(item["date"], 0) + float(item["amount"] or 0)
    by_day = {c["date"]: c for c in window}
    cost = first["close"] * (1 + commission)
    paid = 0.0
    current = 1.0
    values = []
    for day in dates:
        paid += dividend_map.get(day, 0.0)
        if day in by_day:
            sale_fee = 1 - commission if day == last["date"] else 1
            current = (by_day[day]["close"] * sale_fee + paid) / cost
        values.append(current)
    trade = {"entry_date": first["date"], "exit_date": last["date"],
             "entry_price": first["close"], "exit_price": last["close"],
             "return_pct": (values[-1] - 1) * 100, "exit_reason": "period_end"}
    return np.asarray(values), trade


def trade_metrics(trades: list[dict]) -> dict:
    returns = [t["return_pct"] for t in trades]
    return {"trade_count": len(trades),
            "win_rate_pct": sum(r > 0 for r in returns) / len(returns) * 100 if returns else None,
            "average_trade_pct": float(np.mean(returns)) if returns else None}
