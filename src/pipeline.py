from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import ROOT
from .dividends import load_dividend_history, update_dividends
from .events import (
    build_lock_series,
    enrich_news,
    load_news,
    load_report_calendar,
    load_reviews,
)
from .fetch_data import BASE_DATA_FILE, UPDATES_FILE, load_price_history, update_prices
from .fundamentals import attach_eps_ttm, latest_verified_report, load_reports
from .strategy import run_strategy
from .utils import write_json_atomic
from .valuation import GBMModel, calculate_valuation

DOCS_DATA = ROOT / "docs" / "data"
STOCKS_JSON = DOCS_DATA / "stocks.json"
DASHBOARD_JSON = DOCS_DATA / "dashboard.json"
EVENTS_JSON = DOCS_DATA / "events.json"
REPOSITORY_URL = "https://github.com/jl98swe/Stock_value_algorithm"
MAX_FRONTEND_BARS = 800


def _json_number(value: object, digits: int | None = None) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    if digits is not None:
        number = round(number, digits)
    return int(number) if number.is_integer() and digits == 0 else number


def _iso_date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _iso_timestamp(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def _display_name(ticker: str) -> str:
    value = ticker.removesuffix(".ST")
    return value.replace("-", " ")


def _candles(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in frame.tail(MAX_FRONTEND_BARS).itertuples(index=False):
        rows.append(
            {
                "date": pd.Timestamp(row.date).date().isoformat(),
                "open": _json_number(row.open, 4),
                "high": _json_number(row.high, 4),
                "low": _json_number(row.low, 4),
                "close": _json_number(row.close, 4),
                "volume": _json_number(row.volume, 0),
                "ma200": _json_number(row.ma200, 4),
            }
        )
    return rows


def _valuation_input(price_frame: pd.DataFrame, ticker: str, reports: pd.DataFrame) -> pd.DataFrame:
    frame = price_frame.rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "ma200": "MA200",
        }
    ).copy()
    return attach_eps_ttm(frame, ticker, reports)


def _score_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    if "Score" not in frame.columns:
        return []
    rows: list[dict[str, object]] = []
    for row in frame.tail(MAX_FRONTEND_BARS).itertuples(index=False):
        value = getattr(row, "Score", np.nan)
        rows.append({"date": _iso_date(row.Date), "value": _json_number(value, 4)})
    return rows


def _signal_rows(strategy: dict[str, object] | None) -> list[dict[str, object]]:
    if not strategy:
        return []
    output: list[dict[str, object]] = []
    for signal in strategy.get("signals", []):
        item = dict(signal)
        item["date"] = item.get("signal_date")
        output.append(item)
    return output


def _position_payload(strategy: dict[str, object] | None) -> dict[str, object]:
    default = {
        "lots": 0,
        "max_lots": 2,
        "avg_entry": None,
        "unrealized_pct": None,
        "last_buy_date": None,
        "buy_armed": True,
        "sell_armed": True,
    }
    if not strategy:
        return default

    summary = strategy.get("summary", {})
    lots = strategy.get("open_lots", [])
    state = strategy.get("state")
    quantities = [float(item.get("quantity", 0) or 0) for item in lots]
    total_quantity = sum(quantities)
    avg_entry = None
    if total_quantity > 0:
        avg_entry = sum(
            float(item.get("entry_price", 0) or 0) * float(item.get("quantity", 0) or 0)
            for item in lots
        ) / total_quantity

    executed_buys = [
        signal for signal in strategy.get("signals", [])
        if signal.get("side") == "BUY" and signal.get("status") == "executed"
    ]
    last_buy_date = executed_buys[-1].get("execution_date") if executed_buys else None

    buy_armed = True
    sell_armed = True
    if isinstance(state, pd.DataFrame) and not state.empty:
        buy_armed = bool(state.iloc[-1].get("BuyArmed", True))
        sell_armed = bool(state.iloc[-1].get("SellArmed", True))

    return {
        "lots": int(summary.get("active_lots", len(lots)) or 0),
        "max_lots": 2,
        "avg_entry": _json_number(avg_entry, 4),
        "unrealized_pct": _json_number(summary.get("unrealized_pct"), 4),
        "last_buy_date": last_buy_date,
        "buy_armed": buy_armed,
        "sell_armed": sell_armed,
    }


def _next_action(strategy: dict[str, object] | None, score_ready: bool) -> dict[str, object]:
    if not score_ready:
        return {
            "type": "NONE",
            "label": "Ingen signal",
            "detail": "Score aktiveras när verifierad EPS TTM och GBM-modellen finns.",
        }
    if not strategy:
        return {"type": "NONE", "label": "Ingen signal", "detail": "Ingen exekverbar signal."}

    pending = strategy.get("summary", {}).get("pending_signal")
    if not pending:
        return {"type": "NONE", "label": "Ingen signal", "detail": "Ingen signal vid senaste stängning."}

    side = str(pending.get("side", ""))
    label = "Köp nästa öppning" if side == "BUY" else "Sälj nästa öppning"
    execute_on = pending.get("execute_on")
    detail = f"Score {float(pending.get('score', 0)):.2f}"
    if execute_on:
        detail += f" · planerad {execute_on}"
    else:
        detail += " · väntar på nästa handelsdag"
    return {"type": side, "label": label, "detail": detail}


def _report_payload(ticker: str, reports: pd.DataFrame, calendar: pd.DataFrame) -> dict[str, object]:
    latest = latest_verified_report(ticker, reports)
    next_report = None
    now = pd.Timestamp.now(tz="UTC")
    future = calendar.loc[
        (calendar["ticker"] == ticker)
        & calendar["scheduled_at"].notna()
        & (calendar["scheduled_at"] >= now)
    ].sort_values("scheduled_at")
    if not future.empty:
        next_report = _iso_timestamp(future.iloc[0]["scheduled_at"])

    if latest is None:
        return {
            "period": None,
            "eps_ttm": None,
            "effective_date": None,
            "verified": False,
            "next_report": next_report,
        }
    return {
        "period": str(latest.get("report_period") or ""),
        "eps_ttm": _json_number(latest.get("eps_ttm"), 6),
        "effective_date": _iso_date(latest.get("effective_date")),
        "verified": bool(latest.get("verified", False)),
        "next_report": next_report,
    }


def _strategy_comparison(strategy: dict[str, object] | None) -> list[dict[str, object]]:
    if not strategy:
        return []
    summary = strategy.get("summary", {})
    return [
        {
            "strategy": "Originalstrategi",
            "return_pct": _json_number(summary.get("total_return_pct"), 2),
            "max_drawdown_pct": _json_number(summary.get("max_drawdown_pct"), 2),
            "trades": int(summary.get("closed_lots", 0) or 0),
            "win_rate_pct": _json_number(summary.get("win_rate_pct"), 2),
        }
    ]


def _stock_payload(
    ticker: str,
    frame: pd.DataFrame,
    reports: pd.DataFrame,
    reviews: list[dict[str, object]],
    calendar: pd.DataFrame,
    model: GBMModel | None,
) -> tuple[dict[str, object], dict[str, object]]:
    frame = frame.sort_values("date").reset_index(drop=True)
    latest_price = frame.iloc[-1]
    previous_close = frame.iloc[-2]["close"] if len(frame) > 1 else np.nan
    change_pct = (
        (float(latest_price["close"]) / float(previous_close) - 1.0) * 100.0
        if pd.notna(previous_close) and float(previous_close) != 0
        else np.nan
    )

    news = load_news(ticker)
    working = _valuation_input(frame, ticker, reports)
    locks = build_lock_series(
        working["Date"],
        ticker,
        news,
        reviews,
        reports,
        calendar,
    )
    working = working.merge(locks[["Date", "FundamentalLock", "LockReason"]], on="Date", how="left")
    working["FundamentalLock"] = working["FundamentalLock"].fillna(False).astype(bool)
    working["LockReason"] = working["LockReason"].fillna("")

    valued: pd.DataFrame | None = None
    strategy: dict[str, object] | None = None
    has_verified_eps = bool(pd.to_numeric(working["EPS_TTM"], errors="coerce").notna().any())
    if model is not None and has_verified_eps:
        valued = calculate_valuation(working, model=model)
        # Bevara låsen efter valuation, som i sin tur bevarar övriga kolumner.
        valued["FundamentalLock"] = working["FundamentalLock"].to_numpy()
        valued["LockReason"] = working["LockReason"].to_numpy()
        if valued["Score"].notna().any():
            strategy = run_strategy(valued, ticker)

    latest_working = valued.iloc[-1] if valued is not None else working.iloc[-1]
    latest_score = _json_number(latest_working.get("Score"), 4)
    latest_eps = _json_number(latest_working.get("EPS_TTM"), 6)
    latest_pe = _json_number(latest_working.get("PE_TTM"), 4)
    latest_zone = str(latest_working.get("PriceZone") or "") if latest_score is not None else "Väntar på verifierad EPS"
    locked = bool(latest_working.get("FundamentalLock", False))
    lock_reason = str(latest_working.get("LockReason", "") or "")
    score_ready = latest_score is not None

    data_quality = "price_verified_eps_ready" if score_ready else "price_verified_eps_pending"
    ticker_meta = {
        "ticker": ticker,
        "name": _display_name(ticker),
        "currency": "SEK",
        "market": "Stockholm",
        "data_quality": data_quality,
        "latest_date": _iso_date(latest_price["date"]),
        "latest_close": _json_number(latest_price["close"], 4),
        "latest_score": latest_score,
        "locked": locked,
    }

    report_payload = _report_payload(ticker, reports, calendar)
    dashboard_stock = {
        "latest": {
            "date": _iso_date(latest_price["date"]),
            "close": _json_number(latest_price["close"], 4),
            "change_pct": _json_number(change_pct, 4),
            "score": latest_score,
            "eps_ttm": latest_eps,
            "pe_ttm": latest_pe,
            "zone": latest_zone,
            "fundamental_lock": locked,
            "lock_reason": lock_reason,
        },
        "candles": _candles(frame),
        "scores": _score_rows(valued) if valued is not None else [],
        "signals": _signal_rows(strategy),
        "position": _position_payload(strategy),
        "next_action": _next_action(strategy, score_ready),
        "report": report_payload,
        "strategy_comparison": _strategy_comparison(strategy),
        "closed_trades": strategy.get("trades", []) if strategy else [],
    }
    return ticker_meta, dashboard_stock


def _dividend_events(dividends: pd.DataFrame) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for row in dividends.itertuples(index=False):
        day = _iso_date(row.ex_date)
        amount = _json_number(row.dividend, 6)
        events.append(
            {
                "event_id": f"dividend:{row.ticker}:{day}",
                "ticker": row.ticker,
                "published_at": f"{day}T00:00:00+02:00",
                "event_date": day,
                "ex_date": day,
                "event_type": "dividend",
                "categories": ["dividend"],
                "source": "Yahoo Finance",
                "title": f"Utdelning {amount:g} SEK" if amount is not None else "Utdelning",
                "summary": "Historisk ex-dag för kontantutdelning.",
                "link": "",
                "is_regulatory": False,
                "review_status": "not_required",
                "classification": "dividend",
                "lock_action": "none",
                "locking": False,
                "review_note": "",
            }
        )
    return events


def _report_events(reports: pd.DataFrame) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for row in reports.itertuples(index=False):
        published_at = _iso_timestamp(row.published_at)
        effective_date = _iso_date(row.effective_date)
        if not published_at and not effective_date:
            continue
        period = str(row.report_period)
        events.append(
            {
                "event_id": f"report:{row.ticker}:{period}",
                "ticker": row.ticker,
                "published_at": published_at or f"{effective_date}T00:00:00+02:00",
                "event_date": effective_date or (published_at or "")[:10],
                "event_type": "report",
                "categories": ["report", "earnings"],
                "source": str(row.source or "Rapportdata"),
                "title": f"Rapport {period}",
                "summary": str(row.notes or ""),
                "link": "",
                "is_regulatory": True,
                "review_status": "reviewed" if bool(row.verified) else "unreviewed",
                "classification": "report_release",
                "lock_action": "release" if bool(row.verified) else "lock_until_verified_report",
                "locking": not bool(row.verified),
                "review_note": "Verifierad EPS TTM" if bool(row.verified) else "Väntar på verifierad EPS TTM",
            }
        )
    return events


def _news_events(tickers: list[str], reviews: list[dict[str, object]]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for ticker in tickers:
        for item in enrich_news(ticker, load_news(ticker), reviews):
            entry = dict(item)
            entry["event_type"] = "news"
            entry.setdefault("categories", ["news"])
            action = str(entry.get("lock_action", "none"))
            unreviewed_regulatory = entry.get("review_status") == "unreviewed" and bool(entry.get("is_regulatory"))
            entry["locking"] = bool(unreviewed_regulatory or action == "lock_until_verified_report")
            events.append(entry)
    return events


def build_dashboard(
    base_file: Path = BASE_DATA_FILE,
    updates_file: Path = UPDATES_FILE,
) -> dict[str, object]:
    prices = load_price_history(base_file, updates_file)
    reports = load_reports()
    reviews = load_reviews()
    calendar = load_report_calendar()
    dividends = load_dividend_history()
    generated_at = datetime.now(ZoneInfo("Europe/Stockholm")).isoformat(timespec="seconds")

    try:
        model = GBMModel.load()
        model_status = "ready"
    except FileNotFoundError:
        model = None
        model_status = "missing"

    stock_list: list[dict[str, object]] = []
    dashboard_stocks: dict[str, object] = {}
    tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())
    for ticker, group in prices.groupby("ticker", sort=True):
        meta, payload = _stock_payload(str(ticker), group, reports, reviews, calendar, model)
        stock_list.append(meta)
        dashboard_stocks[str(ticker)] = payload

    rules = {
        "buy_score": 0,
        "sell_score": 100,
        "cooldown_trading_days": 5,
        "max_buys_per_cycle": 2,
        "execution": "Nästa handelsdags öppning",
        "shorting": False,
        "update_time": "17:45 Europe/Stockholm",
    }

    ready_count = sum(item.get("latest_score") is not None for item in stock_list)
    write_json_atomic(
        STOCKS_JSON,
        {"generated_at": generated_at, "is_demo": False, "stocks": stock_list},
    )
    dashboard_payload = {
        "meta": {
            "generated_at": generated_at,
            "is_demo": False,
            "repository_url": REPOSITORY_URL,
            "data_status": "valuation_ready" if ready_count else "price_live_eps_pending",
            "valuation_model": model_status,
            "stocks_with_score": ready_count,
            "frontend_bars_per_stock": MAX_FRONTEND_BARS,
            "rules": rules,
        },
        "stocks": dashboard_stocks,
    }
    write_json_atomic(DASHBOARD_JSON, dashboard_payload)

    all_events = _dividend_events(dividends) + _report_events(reports) + _news_events(tickers, reviews)
    all_events.sort(key=lambda item: str(item.get("published_at", "")), reverse=True)
    write_json_atomic(
        EVENTS_JSON,
        {"generated_at": generated_at, "is_demo": False, "events": all_events},
    )

    print(
        f"Byggde GitHub Pages-data för {len(stock_list)} aktier, "
        f"{ready_count} med aktiv score och {len(all_events)} E/D/N-händelser. "
        f"Senaste prisdatum: {prices['date'].max().date()}"
    )
    if model is None:
        print("INFO: GBM-modellen saknas. Pris, MA200, utdelningar och event visas, men score väntar.")
    return dashboard_payload


def run(
    *,
    skip_fetch: bool = False,
    full: bool = False,
    skip_dividends: bool = False,
    base_file: Path = BASE_DATA_FILE,
    updates_file: Path = UPDATES_FILE,
) -> None:
    if not skip_fetch:
        update_prices(base_file, updates_file, full=full)
    if not skip_dividends:
        update_dividends()
    build_dashboard(base_file, updates_file)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daglig pipeline: priser + utdelningar + fundamenta -> GitHub Pages-data."
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Bygg utan att hämta nya priser.")
    parser.add_argument("--skip-dividends", action="store_true", help="Hoppa över Yahoo-utdelningar.")
    parser.add_argument("--full", action="store_true", help="Hämta om Yahoo-prisserien före byggning.")
    parser.add_argument("--base-file", type=Path, default=BASE_DATA_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_FILE)
    args = parser.parse_args()
    run(
        skip_fetch=args.skip_fetch,
        full=args.full,
        skip_dividends=args.skip_dividends,
        base_file=args.base_file,
        updates_file=args.updates_file,
    )


if __name__ == "__main__":
    main()
