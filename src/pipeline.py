from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import ROOT
from .fetch_data import BASE_DATA_FILE, UPDATES_FILE, load_price_history, update_prices
from .utils import write_json_atomic

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


def _stock_payload(ticker: str, frame: pd.DataFrame) -> tuple[dict[str, object], dict[str, object]]:
    frame = frame.sort_values("date").reset_index(drop=True)
    latest = frame.iloc[-1]
    previous_close = frame.iloc[-2]["close"] if len(frame) > 1 else np.nan
    change_pct = (
        (float(latest["close"]) / float(previous_close) - 1.0) * 100.0
        if pd.notna(previous_close) and float(previous_close) != 0
        else np.nan
    )

    ticker_meta = {
        "ticker": ticker,
        "name": _display_name(ticker),
        "currency": "SEK",
        "market": "Stockholm",
        "data_quality": "price_verified_eps_pending",
        "latest_date": pd.Timestamp(latest["date"]).date().isoformat(),
        "latest_close": _json_number(latest["close"], 4),
        "latest_score": None,
        "locked": False,
    }

    dashboard_stock = {
        "latest": {
            "date": pd.Timestamp(latest["date"]).date().isoformat(),
            "close": _json_number(latest["close"], 4),
            "change_pct": _json_number(change_pct, 4),
            "score": None,
            "eps_ttm": None,
            "pe_ttm": None,
            "zone": "Väntar på verifierad EPS",
            "fundamental_lock": False,
            "lock_reason": "",
        },
        "candles": _candles(frame),
        "scores": [],
        "signals": [],
        "position": {
            "lots": 0,
            "max_lots": 2,
            "avg_entry": None,
            "unrealized_pct": None,
            "last_buy_date": None,
            "buy_armed": True,
            "sell_armed": True,
        },
        "next_action": {
            "type": "NONE",
            "label": "Ingen signal",
            "detail": "Score aktiveras när verifierad EPS TTM finns.",
        },
        "report": {
            "period": None,
            "eps_ttm": None,
            "effective_date": None,
            "verified": False,
            "next_report": None,
        },
        "strategy_comparison": [],
        "closed_trades": [],
    }
    return ticker_meta, dashboard_stock


def build_dashboard(
    base_file: Path = BASE_DATA_FILE,
    updates_file: Path = UPDATES_FILE,
) -> dict[str, object]:
    prices = load_price_history(base_file, updates_file)
    generated_at = datetime.now(ZoneInfo("Europe/Stockholm")).isoformat(timespec="seconds")

    stock_list: list[dict[str, object]] = []
    dashboard_stocks: dict[str, object] = {}
    for ticker, group in prices.groupby("ticker", sort=True):
        meta, payload = _stock_payload(str(ticker), group)
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

    write_json_atomic(
        STOCKS_JSON,
        {"generated_at": generated_at, "is_demo": False, "stocks": stock_list},
    )
    dashboard_payload = {
        "meta": {
            "generated_at": generated_at,
            "is_demo": False,
            "repository_url": REPOSITORY_URL,
            "data_status": "price_live_eps_pending",
            "frontend_bars_per_stock": MAX_FRONTEND_BARS,
            "rules": rules,
        },
        "stocks": dashboard_stocks,
    }
    write_json_atomic(DASHBOARD_JSON, dashboard_payload)

    if not EVENTS_JSON.exists() or "DEMO-" in EVENTS_JSON.read_text(encoding="utf-8", errors="ignore"):
        write_json_atomic(
            EVENTS_JSON,
            {"generated_at": generated_at, "is_demo": False, "events": []},
        )

    print(
        f"Byggde GitHub Pages-data för {len(stock_list)} aktier. "
        f"Senaste prisdatum: {prices['date'].max().date()}"
    )
    return dashboard_payload


def run(
    *,
    skip_fetch: bool = False,
    full: bool = False,
    base_file: Path = BASE_DATA_FILE,
    updates_file: Path = UPDATES_FILE,
) -> None:
    if not skip_fetch:
        update_prices(base_file, updates_file, full=full)
    build_dashboard(base_file, updates_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daglig pipeline: Yahoo-priser -> GitHub Pages-data.")
    parser.add_argument("--skip-fetch", action="store_true", help="Bygg bara JSON från befintlig prisdata.")
    parser.add_argument("--full", action="store_true", help="Hämta om Yahoo-prisserien före byggning.")
    parser.add_argument("--base-file", type=Path, default=BASE_DATA_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_FILE)
    args = parser.parse_args()
    run(
        skip_fetch=args.skip_fetch,
        full=args.full,
        base_file=args.base_file,
        updates_file=args.updates_file,
    )


if __name__ == "__main__":
    main()
