"""Signal state machine and next-open execution simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .utils import normalize_date_column


@dataclass(frozen=True)
class StrategyParameters:
    buy_threshold: float = 0.0
    sell_threshold: float = 100.0
    threshold_epsilon: float = 1e-9
    cooldown_trading_days: int = 5
    max_lots: int = 2
    sell_lot_policy: str = "fifo"
    respect_fundamental_locks: bool = True
    initial_capital: float = 1.0


@dataclass
class Lot:
    lot_id: str
    cycle_id: int
    entry_signal_date: str
    entry_date: str
    entry_index: int
    entry_price: float
    quantity: float


def _cooldown_ok(current_index: int, previous_index: int | None, minimum_days: int) -> bool:
    # Index distance is the number of observed trading-session steps.
    return previous_index is None or current_index - previous_index >= minimum_days


def _signal_id(ticker: str, date_value: str, side: str, sequence: int) -> str:
    safe = ticker.replace(".", "-")
    return f"{safe}-{date_value}-{side.lower()}-{sequence}"


def run_strategy(
    frame: pd.DataFrame,
    ticker: str,
    *,
    params: StrategyParameters | None = None,
) -> dict[str, Any]:
    """Run the strategy over daily closes and execute at the next session open.

    Rules:
    * buy when the clipped score is 0 (or configured threshold);
    * sell when it is 100, but only while a position exists;
    * the score must leave and re-enter the same-side boundary before another
      same-side signal can occur;
    * buy and sell cooldowns are independent and measured in trading rows;
    * a cooldown-delayed re-entry remains eligible if the score stays at the
      boundary until the five-day minimum has elapsed;
    * at most two buy lots are allowed in one position cycle;
    * a fundamental lock blocks or cancels a signal without consuming the
      threshold event, so it may fire after verified EPS arrives.
    """

    p = params or StrategyParameters()
    data = normalize_date_column(frame)
    for column in ("Open", "Close", "Score"):
        if column not in data.columns:
            raise ValueError(f"Missing strategy column: {column}")
    if "FundamentalLock" not in data.columns:
        data["FundamentalLock"] = False
    if "LockReason" not in data.columns:
        data["LockReason"] = ""

    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    open_lots: list[Lot] = []
    pending: dict[str, Any] | None = None

    buy_armed = True
    sell_armed = True
    buy_block_logged = False
    sell_block_logged = False
    buy_deferred_logged = False
    sell_deferred_logged = False
    last_buy_signal_index: int | None = None
    last_sell_signal_index: int | None = None
    buys_in_cycle = 0
    cycle_id = 0
    signal_sequence = 0
    lot_sequence = 0
    cash = p.initial_capital
    state_rows: list[dict[str, Any]] = []

    def add_status_signal(
        *,
        side: str,
        date_string: str,
        score: float,
        status: str,
        reason: str,
    ) -> None:
        nonlocal signal_sequence
        signal_sequence += 1
        signals.append(
            {
                "signal_id": _signal_id(ticker, date_string, f"{side}-{status}", signal_sequence),
                "ticker": ticker,
                "side": side,
                "signal_date": date_string,
                "score": score,
                "status": status,
                "status_reason": reason,
                "execute_on": None,
            }
        )

    for index, row in data.iterrows():
        date_string = pd.Timestamp(row["Date"]).date().isoformat()
        open_price = float(row["Open"]) if pd.notna(row["Open"]) else np.nan
        close_price = float(row["Close"]) if pd.notna(row["Close"]) else np.nan
        score = float(row["Score"]) if pd.notna(row["Score"]) else np.nan
        locked = bool(row.get("FundamentalLock", False)) and p.respect_fundamental_locks
        lock_reason = str(row.get("LockReason", "") or "")
        executed_today: list[str] = []
        signal_today: list[str] = []
        awaiting_side = ""

        # Execute the prior close's signal at this session's open. A newly
        # discovered lock cancels it before any simulated trade is made.
        if pending is not None and pending["execute_index"] == index:
            signal = signals[pending["signal_list_index"]]
            side = str(signal["side"])
            restore_arm = False
            if locked:
                signal.update(
                    {
                        "status": "cancelled_lock",
                        "execution_date": date_string,
                        "execution_price": None,
                        "status_reason": lock_reason or "Fundamental handelsspärr",
                    }
                )
                restore_arm = True
            elif not np.isfinite(open_price) or open_price <= 0:
                signal.update(
                    {
                        "status": "cancelled_no_open",
                        "execution_date": date_string,
                        "execution_price": None,
                        "status_reason": "Öppningskurs saknas",
                    }
                )
                restore_arm = True
            elif side == "BUY":
                if buys_in_cycle >= p.max_lots or len(open_lots) >= p.max_lots:
                    signal.update(
                        {
                            "status": "cancelled_capacity",
                            "execution_date": date_string,
                            "execution_price": None,
                            "status_reason": "Max antal delposter uppnått",
                        }
                    )
                else:
                    nav_at_open = cash + sum(lot.quantity * open_price for lot in open_lots)
                    target_allocation = nav_at_open / p.max_lots
                    allocation = min(cash, target_allocation)
                    if allocation <= 0:
                        signal.update(
                            {
                                "status": "cancelled_cash",
                                "execution_date": date_string,
                                "execution_price": None,
                                "status_reason": "Inget modellkapital tillgängligt",
                            }
                        )
                        restore_arm = True
                    else:
                        if not open_lots and buys_in_cycle == 0:
                            cycle_id += 1
                        lot_sequence += 1
                        quantity = allocation / open_price
                        lot = Lot(
                            lot_id=f"{ticker.replace('.', '-')}-lot-{lot_sequence}",
                            cycle_id=cycle_id,
                            entry_signal_date=signal["signal_date"],
                            entry_date=date_string,
                            entry_index=index,
                            entry_price=open_price,
                            quantity=quantity,
                        )
                        open_lots.append(lot)
                        cash -= allocation
                        buys_in_cycle += 1
                        signal.update(
                            {
                                "status": "executed",
                                "execution_date": date_string,
                                "execution_price": open_price,
                                "lot_id": lot.lot_id,
                                "quantity": quantity,
                            }
                        )
                        executed_today.append("BUY")
            else:  # SELL
                if not open_lots:
                    signal.update(
                        {
                            "status": "cancelled_no_position",
                            "execution_date": date_string,
                            "execution_price": None,
                            "status_reason": "Ingen aktiv position",
                        }
                    )
                    restore_arm = True
                else:
                    lot_index = 0 if p.sell_lot_policy.lower() == "fifo" else -1
                    lot = open_lots.pop(lot_index)
                    proceeds = lot.quantity * open_price
                    cash += proceeds
                    return_pct = (open_price / lot.entry_price - 1.0) * 100.0
                    trades.append(
                        {
                            "ticker": ticker,
                            "cycle_id": lot.cycle_id,
                            "lot_id": lot.lot_id,
                            "entry_signal_date": lot.entry_signal_date,
                            "entry_date": lot.entry_date,
                            "entry_price": lot.entry_price,
                            "exit_signal_date": signal["signal_date"],
                            "exit_date": date_string,
                            "exit_price": open_price,
                            "quantity": lot.quantity,
                            "return_pct": return_pct,
                            "holding_trading_days": index - lot.entry_index,
                            "status": "closed",
                        }
                    )
                    signal.update(
                        {
                            "status": "executed",
                            "execution_date": date_string,
                            "execution_price": open_price,
                            "lot_id": lot.lot_id,
                            "quantity": lot.quantity,
                        }
                    )
                    executed_today.append("SELL")
                    if not open_lots:
                        buys_in_cycle = 0

            if restore_arm:
                if side == "BUY":
                    buy_armed = True
                    last_buy_signal_index = pending.get("previous_same_side_signal_index")
                else:
                    sell_armed = True
                    last_sell_signal_index = pending.get("previous_same_side_signal_index")
            pending = None

        # Rearm only after leaving the relevant boundary. Separate bookkeeping
        # prevents one blocked/deferred marker from being emitted every day.
        if np.isfinite(score):
            if score > p.buy_threshold + p.threshold_epsilon:
                buy_armed = True
                buy_block_logged = False
                buy_deferred_logged = False
            if score < p.sell_threshold - p.threshold_epsilon:
                sell_armed = True
                sell_block_logged = False
                sell_deferred_logged = False
        if not locked:
            buy_block_logged = False
            sell_block_logged = False

        # Evaluate today's close for a next-open signal.
        if np.isfinite(score):
            buy_hit = score <= p.buy_threshold + p.threshold_epsilon
            sell_hit = score >= p.sell_threshold - p.threshold_epsilon

            if buy_hit and buy_armed:
                capacity_ok = buys_in_cycle < p.max_lots and len(open_lots) < p.max_lots
                cooldown_ok = _cooldown_ok(index, last_buy_signal_index, p.cooldown_trading_days)
                # A fundamental lock is the primary reason no order may be
                # created. Capacity and cooldown are evaluated only after the
                # information state is safe, which keeps the audit trail clear.
                if locked:
                    if not buy_block_logged:
                        add_status_signal(
                            side="BUY",
                            date_string=date_string,
                            score=score,
                            status="blocked",
                            reason=lock_reason or "Fundamental handelsspärr",
                        )
                        signal_today.append("BUY_BLOCKED")
                        buy_block_logged = True
                elif not capacity_ok:
                    add_status_signal(
                        side="BUY",
                        date_string=date_string,
                        score=score,
                        status="suppressed_capacity",
                        reason="Max antal köp i positionscykeln",
                    )
                    buy_armed = False
                elif not cooldown_ok:
                    if not buy_deferred_logged:
                        add_status_signal(
                            side="BUY",
                            date_string=date_string,
                            score=score,
                            status="deferred_cooldown",
                            reason=f"Väntar tills {p.cooldown_trading_days} handelsdagar har gått",
                        )
                        buy_deferred_logged = True
                elif pending is None:
                    signal_sequence += 1
                    execute_index = index + 1 if index + 1 < len(data) else None
                    previous_same_side = last_buy_signal_index
                    signal = {
                        "signal_id": _signal_id(ticker, date_string, "BUY", signal_sequence),
                        "ticker": ticker,
                        "side": "BUY",
                        "signal_date": date_string,
                        "score": score,
                        "status": "pending" if execute_index is not None else "awaiting_next_session",
                        "status_reason": "",
                        "execute_on": (
                            pd.Timestamp(data.iloc[execute_index]["Date"]).date().isoformat() if execute_index is not None else None
                        ),
                    }
                    signals.append(signal)
                    buy_armed = False
                    buy_deferred_logged = False
                    last_buy_signal_index = index
                    signal_today.append("BUY")
                    if execute_index is not None:
                        pending = {
                            "execute_index": execute_index,
                            "signal_list_index": len(signals) - 1,
                            "previous_same_side_signal_index": previous_same_side,
                        }
                    else:
                        awaiting_side = "BUY"

            # A single close cannot be both the configured buy and sell boundary.
            if sell_hit and sell_armed and open_lots:
                cooldown_ok = _cooldown_ok(index, last_sell_signal_index, p.cooldown_trading_days)
                if locked:
                    if not sell_block_logged:
                        add_status_signal(
                            side="SELL",
                            date_string=date_string,
                            score=score,
                            status="blocked",
                            reason=lock_reason or "Fundamental handelsspärr",
                        )
                        signal_today.append("SELL_BLOCKED")
                        sell_block_logged = True
                elif not cooldown_ok:
                    if not sell_deferred_logged:
                        add_status_signal(
                            side="SELL",
                            date_string=date_string,
                            score=score,
                            status="deferred_cooldown",
                            reason=f"Väntar tills {p.cooldown_trading_days} handelsdagar har gått",
                        )
                        sell_deferred_logged = True
                elif pending is None:
                    signal_sequence += 1
                    execute_index = index + 1 if index + 1 < len(data) else None
                    previous_same_side = last_sell_signal_index
                    signal = {
                        "signal_id": _signal_id(ticker, date_string, "SELL", signal_sequence),
                        "ticker": ticker,
                        "side": "SELL",
                        "signal_date": date_string,
                        "score": score,
                        "status": "pending" if execute_index is not None else "awaiting_next_session",
                        "status_reason": "",
                        "execute_on": (
                            pd.Timestamp(data.iloc[execute_index]["Date"]).date().isoformat() if execute_index is not None else None
                        ),
                    }
                    signals.append(signal)
                    sell_armed = False
                    sell_deferred_logged = False
                    last_sell_signal_index = index
                    signal_today.append("SELL")
                    if execute_index is not None:
                        pending = {
                            "execute_index": execute_index,
                            "signal_list_index": len(signals) - 1,
                            "previous_same_side_signal_index": previous_same_side,
                        }
                    else:
                        awaiting_side = "SELL"

        market_value = sum(lot.quantity * close_price for lot in open_lots) if np.isfinite(close_price) else np.nan
        equity = cash + market_value if np.isfinite(market_value) else np.nan
        weighted_cost = sum(lot.quantity * lot.entry_price for lot in open_lots)
        unrealized_pct = (
            (market_value / weighted_cost - 1.0) * 100.0
            if open_lots and weighted_cost > 0 and np.isfinite(market_value)
            else np.nan
        )
        pending_side = signals[pending["signal_list_index"]]["side"] if pending is not None else awaiting_side
        state_rows.append(
            {
                "Date": row["Date"],
                "PositionLots": len(open_lots),
                "BuysInCycle": buys_in_cycle,
                "BuyArmed": buy_armed,
                "SellArmed": sell_armed,
                "Cash": cash,
                "MarketValue": market_value,
                "Equity": equity,
                "StrategyReturnPct": (equity / p.initial_capital - 1.0) * 100.0 if np.isfinite(equity) else np.nan,
                "UnrealizedPct": unrealized_pct,
                "SignalToday": ",".join(signal_today),
                "ExecutedToday": ",".join(executed_today),
                "PendingSide": pending_side,
            }
        )

    state = pd.DataFrame(state_rows)
    completed_returns = [float(trade["return_pct"]) for trade in trades]
    wins = sum(value > 0 for value in completed_returns)
    equity_values = state["Equity"].dropna()
    if equity_values.empty:
        max_drawdown = None
    else:
        running_max = equity_values.cummax()
        max_drawdown = float(((equity_values / running_max - 1.0) * 100.0).min())

    outstanding = next(
        (signal for signal in reversed(signals) if signal.get("status") in {"pending", "awaiting_next_session"}),
        None,
    )
    summary = {
        "ticker": ticker,
        "ending_equity": float(state.iloc[-1]["Equity"]) if not state.empty and pd.notna(state.iloc[-1]["Equity"]) else None,
        "total_return_pct": (
            float(state.iloc[-1]["StrategyReturnPct"])
            if not state.empty and pd.notna(state.iloc[-1]["StrategyReturnPct"])
            else None
        ),
        "max_drawdown_pct": max_drawdown,
        "closed_lots": len(trades),
        "win_rate_pct": (wins / len(completed_returns) * 100.0) if completed_returns else None,
        "average_trade_pct": float(np.mean(completed_returns)) if completed_returns else None,
        "active_lots": len(open_lots),
        "unrealized_pct": (
            float(state.iloc[-1]["UnrealizedPct"])
            if not state.empty and pd.notna(state.iloc[-1]["UnrealizedPct"])
            else None
        ),
        "pending_signal": outstanding,
    }

    latest_close = float(data.iloc[-1]["Close"]) if not data.empty and pd.notna(data.iloc[-1]["Close"]) else np.nan
    open_lot_payload = [
        {
            "lot_id": lot.lot_id,
            "cycle_id": lot.cycle_id,
            "entry_signal_date": lot.entry_signal_date,
            "entry_date": lot.entry_date,
            "entry_price": lot.entry_price,
            "quantity": lot.quantity,
            "current_return_pct": ((latest_close / lot.entry_price - 1.0) * 100.0 if np.isfinite(latest_close) else None),
        }
        for lot in open_lots
    ]
    return {
        "state": state,
        "signals": signals,
        "trades": trades,
        "open_lots": open_lot_payload,
        "summary": summary,
    }
