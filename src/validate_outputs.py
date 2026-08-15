from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .fetch_data import BASE_DATA_FILE, PRICE_COLUMNS, UPDATES_FILE, load_price_history
from .fundamentals import load_reports, verified_reports
from .model_data import ensure_gbm_model
from .valuation import GBMModel

DOCS_DATA = ROOT / "docs" / "data"


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f"Saknad eller tom JSON-fil: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Förväntade JSON-objekt i {path}")
    return payload


def _validate_price_updates(prices: pd.DataFrame) -> None:
    target = ROOT / UPDATES_FILE if not UPDATES_FILE.is_absolute() else UPDATES_FILE
    if not target.exists() or target.stat().st_size == 0:
        return

    updates = pd.read_csv(target)
    expected = PRICE_COLUMNS
    missing = [column for column in expected if column not in updates.columns]
    if missing:
        raise ValueError(f"price_updates.csv saknar kolumner: {', '.join(missing)}")

    updates["date"] = pd.to_datetime(updates["date"], errors="coerce").dt.tz_localize(None)
    if updates[["date", "ticker", "close"]].isna().any().any():
        raise ValueError("price_updates.csv innehåller saknat datum, ticker eller close")
    if updates.duplicated(["ticker", "date"]).any():
        raise ValueError("price_updates.csv innehåller dubbla ticker+date")

    expected_ma = prices[["ticker", "date", "ma200"]].rename(columns={"ma200": "expected_ma200"})
    check = updates.merge(expected_ma, on=["ticker", "date"], how="left")
    actual = pd.to_numeric(check["ma200"], errors="coerce").to_numpy(dtype=float)
    expected_values = pd.to_numeric(check["expected_ma200"], errors="coerce").to_numpy(dtype=float)
    if not np.allclose(actual, expected_values, equal_nan=True, rtol=1e-10, atol=1e-10):
        raise ValueError("MA200 i price_updates.csv stämmer inte med kombinerad prishistorik")


def _validate_dashboard(prices: pd.DataFrame) -> None:
    stocks_payload = _load_json(DOCS_DATA / "stocks.json")
    dashboard = _load_json(DOCS_DATA / "dashboard.json")
    events = _load_json(DOCS_DATA / "events.json")

    price_tickers = set(prices["ticker"].astype(str).unique())
    stock_rows = stocks_payload.get("stocks", [])
    if not isinstance(stock_rows, list):
        raise ValueError("stocks.json: stocks måste vara en lista")
    listed_tickers = {str(row.get("ticker")) for row in stock_rows if isinstance(row, dict)}
    if listed_tickers != price_tickers:
        raise ValueError(
            f"stocks.json matchar inte prisuniversum: {len(listed_tickers)} vs {len(price_tickers)}"
        )

    dashboard_stocks = dashboard.get("stocks", {})
    if not isinstance(dashboard_stocks, dict) or set(dashboard_stocks) != price_tickers:
        raise ValueError("dashboard.json matchar inte prisuniversum")

    latest_dates = prices.groupby("ticker")["date"].max()
    for ticker in price_tickers:
        payload = dashboard_stocks[ticker]
        if not isinstance(payload, dict):
            raise ValueError(f"Ogiltigt dashboard-objekt för {ticker}")
        latest = payload.get("latest", {})
        if latest.get("date") != latest_dates.loc[ticker].date().isoformat():
            raise ValueError(f"Fel senaste datum i dashboard för {ticker}")
        candles = payload.get("candles", [])
        if not candles:
            raise ValueError(f"Inga candlesticks i dashboard för {ticker}")
        if "ma200" not in candles[-1]:
            raise ValueError(f"MA200 saknas i senaste candlestick för {ticker}")

    meta = dashboard.get("meta", {})
    if meta.get("valuation_model") != "ready":
        raise ValueError(f"GBM-modellen är inte aktiv: {meta.get('valuation_model')}")

    report_store = load_reports()
    verified = verified_reports(report_store)
    ready_count = int(meta.get("stocks_with_score", 0) or 0)
    if verified.empty and ready_count != 0:
        raise ValueError("Dashboard visar score trots att verifierad EPS-historik saknas")

    event_rows = events.get("events", [])
    if not isinstance(event_rows, list):
        raise ValueError("events.json: events måste vara en lista")
    if any("DEMO-" in str(item) for item in event_rows):
        raise ValueError("Demo-event finns kvar i live-data")
    if not any(isinstance(item, dict) and item.get("event_type") == "dividend" for item in event_rows):
        raise ValueError("Inga utdelningshändelser exporterades till events.json")


def validate() -> None:
    model_path = ensure_gbm_model()
    model = GBMModel.load(model_path)
    if len(model.tree_root) != 100:
        raise ValueError(f"GBM-modellen har {len(model.tree_root)} träd, förväntade 100")

    base_path = ROOT / BASE_DATA_FILE if not BASE_DATA_FILE.is_absolute() else BASE_DATA_FILE
    if not base_path.exists():
        raise FileNotFoundError(base_path)

    prices = load_price_history()
    if prices.empty:
        raise ValueError("Kombinerad prishistorik är tom")
    if prices.duplicated(["ticker", "date"]).any():
        raise ValueError("Kombinerad prishistorik innehåller dubbletter")
    if prices["ticker"].nunique() < 1:
        raise ValueError("Prisdata innehåller inga tickers")

    _validate_price_updates(prices)
    _validate_dashboard(prices)
    print(
        f"Validering OK: {prices['ticker'].nunique()} tickers, "
        f"{len(prices):,} prisrader, GBM 100 träd, webbdata konsistent."
    )


if __name__ == "__main__":
    validate()
