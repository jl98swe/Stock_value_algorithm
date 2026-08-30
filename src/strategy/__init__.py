"""Website strategy adapter with strict 1/99 thresholds and net cash accounting.

The package shadows the legacy ``src/strategy.py`` module so existing imports keep
working. The legacy state machine decides when orders are allowed, while this adapter
replays executed orders with strict <1 / >99 boundaries, 0.25% commission on both
sides, and dividends credited to lots held across the ex-date.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..dividends import load_dividend_history
from ..utils import normalize_date_column

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


def _ticker_dividend_map(ticker: str) -> dict[pd.Timestamp, float]:
    history = load_dividend_history()
    if history.empty:
        return {}
    rows = history.loc[history["ticker"].astype(str) == ticker].copy()
    if rows.empty:
        return {}
    rows["ex_date"] = pd.to_datetime(rows["ex_date"], errors="coerce").dt.normalize()
    rows["dividend"] = pd.to_numeric(rows["dividend"], errors="coerce").fillna(0.0)
    return {
        pd.Timestamp(row.ex_date).normalize(): float(row.dividend)
        for row in rows.itertuples(index=False)
        if pd.notna(row.ex_date) and float(row.dividend) > 0
    }


def _strict_default_params() -> StrategyParameters:
    # The legacy engine uses <= and >= together with a 1e-9 epsilon. Moving the
    # configured boundary by 2e-9 makes the effective conditions strictly <1
    # and >99, so exactly 1.00 and 99.00 never trigger.
    return StrategyParameters(
        buy_threshold=BUY_THRESHOLD - _STRICT_OFFSET,
        sell_threshold=SELL_THRESHOLD + _STRICT_OFFSET,
    )


def _replay_net_cashflows(
    frame: pd.DataFrame,
    ticker: str,
    result: dict[str, Any],
    params: StrategyParameters,
) -> None:
    data = normalize_date_column(frame)
    dividends = _ticker_dividend_map(ticker)
    executed = [signal for signal in result.get("signals", []) if signal.get("status") == "executed"]
    by_date: dict[str, list[dict[str, Any]]] = {}
    for signal in executed:
        by_date.setdefault(str(signal.get("execution_date")), []).append(signal)

    cash = float(params.initial_capital)
    open_lots: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    for index, row in data.iterrows():
        day = pd.Timestamp(row["Date"]).normalize()
        day_string = day.date().isoformat()
        open_price = float(row["Open"]) if pd.notna(row["Open"]) else np.nan
        close_price = float(row["Close"]) if pd.notna(row["Close"]) else np.nan

        # Ex-date cash belongs to positions held before today's opening trade.
        dividend_per_share = dividends.get(day, 0.0)
        if dividend_per_share > 0:
            for lot in open_lots:
                dividend_cash = float(lot["quantity"]) * dividend_per_share
                cash += dividend_cash
                lot["dividends_received"] += dividend_cash
                lot["dividend_per_share"] += dividend_per_share

        for signal in by_date.get(day_string, []):
            side = str(signal.get("side", ""))
            execution_price = float(signal.get("execution_price") or open_price)
            if not np.isfinite(execution_price) or execution_price <= 0:
                continue

            if side == "BUY":
                nav_at_open = cash + sum(float(lot["quantity"]) * execution_price for lot in open_lots)
                target_allocation = nav_at_open / max(1, int(params.max_lots))
                total_budget = min(cash, target_allocation)
                if total_budget <= 0:
                    continue
                trade_value = total_budget / (1.0 + COMMISSION_RATE)
                quantity = trade_value / execution_price
                entry_fee = trade_value * COMMISSION_RATE
                cash -= trade_value + entry_fee
                lot = {
                    "lot_id": signal.get("lot_id"),
                    "cycle_id": None,
                    "entry_signal_date": signal.get("signal_date"),
                    "entry_date": day_string,
                    "entry_index": index,
                    "entry_price": execution_price,
                    "quantity": quantity,
                    "entry_fee": entry_fee,
                    "dividends_received": 0.0,
                    "dividend_per_share": 0.0,
                }
                open_lots.append(lot)
                signal["quantity"] = quantity
                signal["commission_fee"] = entry_fee

            elif side == "SELL" and open_lots:
                wanted_lot_id = signal.get("lot_id")
                lot_index = next(
                    (i for i, lot in enumerate(open_lots) if lot.get("lot_id") == wanted_lot_id),
                    0 if str(params.sell_lot_policy).lower() == "fifo" else len(open_lots) - 1,
                )
                lot = open_lots.pop(lot_index)
                quantity = float(lot["quantity"])
                gross_proceeds = quantity * execution_price
                exit_fee = gross_proceeds * COMMISSION_RATE
                net_proceeds = gross_proceeds - exit_fee
                cash += net_proceeds
                entry_cost = quantity * float(lot["entry_price"]) + float(lot["entry_fee"])
                total_value = net_proceeds + float(lot["dividends_received"])
                return_pct = (total_value / entry_cost - 1.0) * 100.0
                trades.append(
                    {
                        "ticker": ticker,
                        "cycle_id": lot.get("cycle_id"),
                        "lot_id": lot.get("lot_id"),
                        "entry_signal_date": lot.get("entry_signal_date"),
                        "entry_date": lot.get("entry_date"),
                        "entry_price": lot.get("entry_price"),
                        "exit_signal_date": signal.get("signal_date"),
                        "exit_date": day_string,
                        "exit_price": execution_price,
                        "quantity": quantity,
                        "entry_fee": float(lot["entry_fee"]),
                        "exit_fee": exit_fee,
                        "commission_total": float(lot["entry_fee"]) + exit_fee,
                        "dividend_per_share": float(lot["dividend_per_share"]),
                        "dividends_received": float(lot["dividends_received"]),
                        "return_pct": return_pct,
                        "holding_trading_days": index - int(lot["entry_index"]),
                        "status": "closed",
                    }
                )
                signal["quantity"] = quantity
                signal["commission_fee"] = exit_fee

        market_value = (
            sum(float(lot["quantity"]) * close_price for lot in open_lots)
            if np.isfinite(close_price)
            else np.nan
        )
        equity = cash + market_value if np.isfinite(market_value) else np.nan
        weighted_cost = sum(
            float(lot["quantity"]) * float(lot["entry_price"]) + float(lot["entry_fee"])
            for lot in open_lots
        )
        accumulated_dividends = sum(float(lot["dividends_received"]) for lot in open_lots)
        unrealized_pct = (
            ((market_value + accumulated_dividends) / weighted_cost - 1.0) * 100.0
            if open_lots and weighted_cost > 0 and np.isfinite(market_value)
            else np.nan
        )
        equity_rows.append(
            {
                "Date": row["Date"],
                "Cash": cash,
                "MarketValue": market_value,
                "Equity": equity,
                "StrategyReturnPct": (
                    (equity / float(params.initial_capital) - 1.0) * 100.0
                    if np.isfinite(equity)
                    else np.nan
                ),
                "UnrealizedPct": unrealized_pct,
            }
        )

    net_state = pd.DataFrame(equity_rows)
    legacy_state = result.get("state")
    if isinstance(legacy_state, pd.DataFrame) and not legacy_state.empty and len(legacy_state) == len(net_state):
        for column in ("Cash", "MarketValue", "Equity", "StrategyReturnPct", "UnrealizedPct"):
            legacy_state[column] = net_state[column].to_numpy()
        result["state"] = legacy_state
    else:
        result["state"] = net_state

    latest_close = float(data.iloc[-1]["Close"]) if not data.empty and pd.notna(data.iloc[-1]["Close"]) else np.nan
    open_lot_payload = []
    for lot in open_lots:
        entry_cost = float(lot["quantity"]) * float(lot["entry_price"]) + float(lot["entry_fee"])
        current_value = (
            float(lot["quantity"]) * latest_close + float(lot["dividends_received"])
            if np.isfinite(latest_close)
            else np.nan
        )
        open_lot_payload.append(
            {
                "lot_id": lot.get("lot_id"),
                "cycle_id": lot.get("cycle_id"),
                "entry_signal_date": lot.get("entry_signal_date"),
                "entry_date": lot.get("entry_date"),
                "entry_price": lot.get("entry_price"),
                "quantity": lot.get("quantity"),
                "entry_fee": lot.get("entry_fee"),
                "dividends_received": lot.get("dividends_received"),
                "current_return_pct": (
                    (current_value / entry_cost - 1.0) * 100.0
                    if np.isfinite(current_value) and entry_cost > 0
                    else None
                ),
            }
        )

    result["trades"] = trades
    result["open_lots"] = open_lot_payload

    returns = [float(trade["return_pct"]) for trade in trades]
    summary = result.get("summary", {})
    equity_values = net_state["Equity"].dropna()
    if equity_values.empty:
        max_drawdown = None
        ending_equity = None
        total_return = None
    else:
        running_max = equity_values.cummax()
        max_drawdown = float(((equity_values / running_max - 1.0) * 100.0).min())
        ending_equity = float(equity_values.iloc[-1])
        total_return = (ending_equity / float(params.initial_capital) - 1.0) * 100.0

    summary.update(
        {
            "ending_equity": ending_equity,
            "total_return_pct": total_return,
            "max_drawdown_pct": max_drawdown,
            "closed_lots": len(trades),
            "win_rate_pct": (sum(value > 0 for value in returns) / len(returns) * 100.0) if returns else None,
            "average_trade_pct": (sum(returns) / len(returns)) if returns else None,
            "active_lots": len(open_lot_payload),
            "unrealized_pct": (
                float(net_state.iloc[-1]["UnrealizedPct"])
                if not net_state.empty and pd.notna(net_state.iloc[-1]["UnrealizedPct"])
                else None
            ),
            "buy_condition": "Score < 1",
            "sell_condition": "Score > 99",
            "commission_buy_pct": 0.25,
            "commission_sell_pct": 0.25,
            "dividends_in_trade_returns": True,
        }
    )
    result["summary"] = summary


def run_strategy(
    frame: pd.DataFrame,
    ticker: str,
    *,
    params: StrategyParameters | None = None,
) -> dict[str, Any]:
    """Run the strategy with strict <1 / >99 signals and net cash accounting."""

    effective_params = params or _strict_default_params()
    result = _LEGACY.run_strategy(frame, ticker, params=effective_params)
    _replay_net_cashflows(frame, ticker, result, effective_params)
    return result


__all__ = ["BUY_THRESHOLD", "SELL_THRESHOLD", "COMMISSION_RATE", "StrategyParameters", "Lot", "run_strategy"]
