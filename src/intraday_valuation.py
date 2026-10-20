"""Disposable today-as-close scores; never writes daily prices or strategy state."""
from __future__ import annotations

import math
import time

import exchange_calendars as xcals
import pandas as pd

from .fundamentals import attach_eps_ttm, load_reports, valuation_calculation_mode
from .model_data import ensure_gbm_model
from .signal_prices import NextCloseScore
from .valuation import GBMModel, price_zone


def add_preliminary_scores(payload, stocks, now, *, prices=None, reports=None, model=None):
    """Replace scores for the exact cached quote using one hypothetical daily row.

    Full EPS/FX history is prepared as in the daily engine, including TradingView
    period-end state. A new report's EPS can differ from yesterday's EPS. All
    intraday refreshes start from completed sessions, never the previous refresh.
    """
    started = time.perf_counter()
    for item in payload.get("stocks", {}).values():
        item.pop("valuation", None)
    if not payload.get("stocks"):
        return payload
    if prices is None:
        from .fetch_data import load_price_history
        prices = load_price_history(as_of=now)
    reports = load_reports() if reports is None else reports
    model = GBMModel.load(ensure_gbm_model()) if model is None else model
    day = pd.Timestamp(payload["session_date"])
    calendar = xcals.get_calendar("XSTO")
    if not calendar.is_session(day):
        return payload
    previous = pd.Timestamp(calendar.previous_session(day)).tz_localize(None)
    meta = {s["ticker"]: s for s in stocks}
    grouped = {str(t): f for t, f in prices.groupby("ticker")}
    count = 0
    for ticker, item in payload["stocks"].items():
        quote = item.get("latest", {})
        stock = meta.get(ticker, {})
        history = grouped.get(ticker)
        if history is None or not stock.get("active_for_updates", True):
            continue
        at = pd.to_datetime(quote.get("as_of"), utc=True, errors="coerce")
        price = quote.get("price")
        if (pd.isna(at) or at.tz_convert("Europe/Stockholm").date() != day.date()
                or at > pd.Timestamp(now) or not isinstance(price, (float, int))
                or not math.isfinite(price) or price <= 0
                or quote.get("currency") != stock.get("currency", "SEK")):
            continue
        history = history.loc[pd.to_datetime(history.date) < day].sort_values("date")
        if (history.empty or pd.Timestamp(history.date.iloc[-1]) != previous
                or str(stock.get("latest_date")) != previous.date().isoformat()):
            continue  # Missing daily observations must not be treated as consecutive days.
        frame = history.rename(columns={"date": "Date", "close": "Close"})[["Date", "Close"]]
        trial = pd.concat([frame, pd.DataFrame({"Date": [day], "Close": [price]})], ignore_index=True)
        known = reports.loc[(reports.effective_date <= day)
                            & (reports.published_at.isna() | (reports.published_at <= at))]
        trial = attach_eps_ttm(trial, ticker, known,
                               calculation_mode=valuation_calculation_mode(ticker, known))
        eps = pd.to_numeric(trial.EPS_TTM, errors="coerce").iloc[-1]
        if not math.isfinite(eps) or eps == 0:
            continue
        predict = NextCloseScore(trial.iloc[:-1], model, eps=eps)
        value = float(predict([price])[0])
        if not math.isfinite(value):
            continue
        ma200 = float(trial.Close.iloc[-200:].mean()) if len(trial) >= 200 else None
        fetched = pd.to_datetime(quote.get("fetched_at"), utc=True, errors="coerce")
        fetched_local = fetched.tz_convert("Europe/Stockholm") if not pd.isna(fetched) else None
        preliminary = (fetched_local is None or fetched_local.date() != day.date()
                       or fetched > pd.Timestamp(now)
                       or (fetched_local.hour, fetched_local.minute) < (17, 30))
        item["valuation"] = {"score": round(value, 4), "zone": price_zone(value),
                             "pe_ttm": float(price / eps), "eps_ttm": float(eps),
                             "ma200": ma200, "price": price, "currency": quote["currency"],
                             "as_of": quote["as_of"], "basis_date": previous.date().isoformat(),
                             "session": day.date().isoformat(), "preliminary": preliminary,
                             "fetched_at": quote.get("fetched_at")}
        count += 1
    payload["valuation_coverage"] = {"available": count, "expected": len(payload["stocks"])}
    print(f"Preliminär poäng: {count}/{len(payload['stocks'])}, {time.perf_counter() - started:.2f} s")
    return payload
