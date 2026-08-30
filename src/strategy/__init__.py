"""Website strategy adapter with strict 1/99 thresholds and net trade returns.

This package intentionally shadows the legacy ``src/strategy.py`` module so existing
imports (``from .strategy import run_strategy``) keep working without rewriting the
pipeline. The legacy state machine is loaded under a private module name and used as
the execution engine. This adapter supplies strict <1 / >99 thresholds, then adjusts
historical trade returns for 0.25% commission on both sides and cash dividends earned
while the lot was held.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from ..dividends import load_dividend_history

_LEGACY_PATH = Path(__file__).resolve().parents[1] / "strategy.py"
_SPEC = importlib.util.spec_from_file_location("src._strategy_legacy", _LEGACY_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Could not load legacy strategy from {_LEGACY_PATH}")
_LEGACY = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _LEGACY
_SPEC.loader.exec_module(_LEGACY)

StrategyParameters = _LEGACY.StrategyParameters
Lot = _LEGACY.Lot

BUY_THRESHOLD = 1.0
SELL_THRESHOLD = 99.0
COMMISSION_RATE = 0.0025
_STRICT_OFFSET = 2e-9


def _dividend_per_share(ticker: str, entry_date: str, exit_date: str) -> float:
    history = load_dividend_history()
    if history.empty:
        return 0.0
    rows = history.loc[history["ticker"].astype(str) == ticker].copy()
    if rows.empty:
        return 0.0
    rows["ex_date"] = pd.to_datetime(rows["ex_date"], errors="coerce").dt.normalize()
    entry = pd.Timestamp(entry_date).normalize()
    exit_ = pd.Timestamp(exit_date).normalize()
    # A lot bought on the ex-date does not receive that dividend; a lot sold on
    # the ex-date does, because it was owned before that session opened.
    held = rows.loc[(rows["ex_date"] > entry) & (rows["ex_date"] <= exit_)]
    return float(pd.to_numeric(held["dividend"], errors="coerce").fillna(0.0).sum())


def _net_trade_return(entry_price: float, exit_price: float, dividend_per_share: float) -> float:
    entry_cost = float(entry_price) * (1.0 + COMMISSION_RATE)
    exit_value = float(exit_price) * (1.0 - COMMISSION_RATE) + float(dividend_per_share)
    return (exit_value / entry_cost - 1.0) * 100.0


def run_strategy(
    frame: pd.DataFrame,
    ticker: str,
    *,
    params: StrategyParameters | None = None,
) -> dict[str, Any]:
    """Run the existing state machine with strict <1 / >99 signal boundaries.

    Historical closed-trade returns are reported net of 0.25% buy commission,
    0.25% sell commission, plus dividends earned during the holding period.
    """

    if params is None:
        # The legacy engine uses <= and >=. Offsetting the thresholds beyond its
        # 1e-9 epsilon makes the effective conditions strictly Score < 1 and
        # Score > 99, so exactly 1.00 and 99.00 do not trigger.
        params = StrategyParameters(
            buy_threshold=BUY_THRESHOLD - _STRICT_OFFSET,
            sell_threshold=SELL_THRESHOLD + _STRICT_OFFSET,
        )

    result = _LEGACY.run_strategy(frame, ticker, params=params)

    for trade in result.get("trades", []):
        entry_price = float(trade["entry_price"])
        exit_price = float(trade["exit_price"])
        quantity = float(trade.get("quantity", 0.0) or 0.0)
        dividend_per_share = _dividend_per_share(
            ticker,
            str(trade["entry_date"]),
            str(trade["exit_date"]),
        )
        entry_fee = quantity * entry_price * COMMISSION_RATE
        exit_fee = quantity * exit_price * COMMISSION_RATE
        dividend_cash = quantity * dividend_per_share
        trade["entry_fee"] = entry_fee
        trade["exit_fee"] = exit_fee
        trade["commission_total"] = entry_fee + exit_fee
        trade["dividend_per_share"] = dividend_per_share
        trade["dividends_received"] = dividend_cash
        trade["return_pct"] = _net_trade_return(entry_price, exit_price, dividend_per_share)

    returns = [float(trade["return_pct"]) for trade in result.get("trades", [])]
    summary = result.get("summary", {})
    if returns:
        summary["win_rate_pct"] = sum(value > 0 for value in returns) / len(returns) * 100.0
        summary["average_trade_pct"] = sum(returns) / len(returns)
    else:
        summary["win_rate_pct"] = None
        summary["average_trade_pct"] = None
    summary["buy_condition"] = "Score < 1"
    summary["sell_condition"] = "Score > 99"
    summary["commission_buy_pct"] = 0.25
    summary["commission_sell_pct"] = 0.25
    summary["dividends_in_trade_returns"] = True
    result["summary"] = summary
    return result


__all__ = ["BUY_THRESHOLD", "SELL_THRESHOLD", "COMMISSION_RATE", "StrategyParameters", "Lot", "run_strategy"]
