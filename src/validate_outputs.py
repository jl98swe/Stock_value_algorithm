from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .earnings import (
    BASE_EARNINGS_FILE,
    EARNINGS_COLUMNS,
    EARNINGS_JSON,
    UPDATES_EARNINGS_FILE,
    load_earnings_history,
)
from .fetch_data import BASE_DATA_FILE, PRICE_COLUMNS, UPDATES_FILE, load_price_history
from .fundamentals import load_reports, verified_reports
from .fx import (
    FX_BASE_FILE,
    FX_COLUMNS,
    FX_UPDATES_FILE,
    load_fx_history,
    load_stock_currencies,
    required_currency_pairs,
)
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


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _validate_price_updates(prices: pd.DataFrame) -> None:
    target = _resolve(UPDATES_FILE)
    if not target.exists() or target.stat().st_size == 0:
        return

    updates = pd.read_csv(target)
    missing = [column for column in PRICE_COLUMNS if column not in updates.columns]
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


def _validate_fx() -> None:
    base_path = _resolve(FX_BASE_FILE)
    if not base_path.exists():
        raise ValueError("fx_initial.csv saknas")

    metadata = load_stock_currencies()
    required_pairs = required_currency_pairs(metadata)
    if not required_pairs:
        return

    for path, label in (
        (base_path, "fx_initial.csv"),
        (_resolve(FX_UPDATES_FILE), "fx_updates.csv"),
    ):
        if not path.exists() or path.stat().st_size == 0:
            continue
        frame = pd.read_csv(path)
        missing = [column for column in FX_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} saknar kolumner: {', '.join(missing)}")

    history = load_fx_history()
    if history.empty:
        raise ValueError("Valutaomräkning krävs men FX-historiken är tom")
    if history.duplicated(["base_currency", "quote_currency", "date"]).any():
        raise ValueError("FX-historiken innehåller dubbla valutapar+datum")

    rates = pd.to_numeric(history["rate"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(rates).all() or (rates <= 0).any():
        raise ValueError("FX-historiken innehåller ogiltiga valutakurser")

    present = set(zip(history["base_currency"], history["quote_currency"]))
    missing_pairs = [pair for pair in required_pairs if pair not in present]
    if missing_pairs:
        raise ValueError(f"Saknar FX-historik för valutapar: {missing_pairs}")


def _validate_earnings(price_tickers: set[str]) -> None:
    base_path = _resolve(BASE_EARNINGS_FILE)
    if not base_path.exists():
        raise ValueError("earnings_initial.csv saknas")

    for path, label in (
        (base_path, "earnings_initial.csv"),
        (_resolve(UPDATES_EARNINGS_FILE), "earnings_updates.csv"),
    ):
        if not path.exists() or path.stat().st_size == 0:
            continue
        frame = pd.read_csv(path)
        missing = [column for column in EARNINGS_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} saknar kolumner: {', '.join(missing)}")
        if frame.empty:
            continue
        frame["observed_date"] = pd.to_datetime(frame["observed_date"], errors="coerce")
        frame["eps_ttm"] = pd.to_numeric(frame["eps_ttm"], errors="coerce")
        if frame[["ticker", "observed_date", "eps_ttm"]].isna().any().any():
            raise ValueError(f"{label} innehåller ogiltig ticker, observed_date eller eps_ttm")
        if frame.duplicated(["ticker", "observed_date"]).any():
            raise ValueError(f"{label} innehåller dubbla ticker+observed_date")

    history = load_earnings_history()
    if history.empty:
        # Tillåtet före den första lyckade EPS-hämtningen.
        return

    unknown = sorted(set(history["ticker"].astype(str)).difference(price_tickers))
    if unknown:
        raise ValueError(f"Earnings innehåller okända tickers: {', '.join(unknown[:10])}")

    payload = _load_json(EARNINGS_JSON)
    rows = payload.get("latest", [])
    if not isinstance(rows, list):
        raise ValueError("earnings.json: latest måste vara en lista")

    latest = (
        history.sort_values(["ticker", "observed_date"])
        .groupby("ticker", sort=False)
        .tail(1)
    )
    if len(rows) != len(latest):
        raise ValueError("earnings.json matchar inte senaste EPS-raderna")

    json_tickers = {str(row.get("ticker")) for row in rows if isinstance(row, dict)}
    if json_tickers != set(latest["ticker"].astype(str)):
        raise ValueError("earnings.json har fel tickeruppsättning")


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

    _validate_earnings(price_tickers)


def validate() -> None:
    model_path = ensure_gbm_model()
    model = GBMModel.load(model_path)
    if len(model.tree_root) != 100:
        raise ValueError(f"GBM-modellen har {len(model.tree_root)} träd, förväntade 100")

    base_path = _resolve(BASE_DATA_FILE)
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
    _validate_fx()
    _validate_dashboard(prices)
    print(
        f"Validering OK: {prices['ticker'].nunique()} tickers, "
        f"{len(prices):,} prisrader, GBM 100 träd, FX och webbdata konsistenta."
    )


if __name__ == "__main__":
    validate()
