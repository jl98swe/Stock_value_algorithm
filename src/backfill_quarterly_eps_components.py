from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .fetch_data import load_price_history
from .quarterly_eps import (
    DILUTED_METRIC,
    QUARTERLY_COLUMNS,
    _publish_json,
    load_quarterly_eps,
    save_quarterly_eps,
)

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
NUMERATOR_TYPES = (
    "quarterlyDilutedNIAvailtoComStockholders",
    "quarterlyNetIncomeCommonStockholders",
)
DENOMINATOR_TYPE = "quarterlyDilutedAverageShares"
SOURCE_PREFIX = "Yahoo Finance / fundamentals-timeseries diluted net income / diluted average shares"


def _universe() -> list[str]:
    prices = load_price_history()
    return sorted(prices["ticker"].dropna().astype(str).str.strip().unique().tolist())


def _values_by_period(payload: dict[str, object], metric: str) -> dict[pd.Timestamp, tuple[float, str]]:
    values: dict[pd.Timestamp, tuple[float, str]] = {}
    for block in (payload.get("timeseries") or {}).get("result") or []:
        items = block.get(metric)
        if not isinstance(items, list):
            continue
        block_currency = str((block.get("meta") or {}).get("currencyCode") or "").strip().upper()
        for item in items:
            period = pd.to_datetime(item.get("asOfDate"), errors="coerce")
            raw = pd.to_numeric((item.get("reportedValue") or {}).get("raw"), errors="coerce")
            if pd.isna(period) or pd.isna(raw) or not math.isfinite(float(raw)):
                continue
            key = pd.Timestamp(period).tz_localize(None).normalize()
            currency = str(item.get("currencyCode") or block_currency or "").strip().upper()
            values[key] = (float(raw), currency)
    return values


def _fetch_one(ticker: str, observed_date: str) -> list[dict[str, object]]:
    now = datetime.now(STOCKHOLM_TZ)
    period1 = int((now - timedelta(days=2200)).timestamp())
    period2 = int((now + timedelta(days=2)).timestamp())
    types = ",".join((*NUMERATOR_TYPES, DENOMINATOR_TYPE))
    url = (
        f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}"
        f"?symbol={ticker}&type={types}&period1={period1}&period2={period2}"
    )
    try:
        response = yf.Ticker(ticker)._data.cache_get(url=url)
        payload = json.loads(response.text)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo component-timeseries kunde inte hämtas: {exc}")
        return []

    denominator = _values_by_period(payload, DENOMINATOR_TYPE)
    numerators = {metric: _values_by_period(payload, metric) for metric in NUMERATOR_TYPES}
    rows: list[dict[str, object]] = []

    for period_end, (shares, _shares_currency) in denominator.items():
        if not math.isfinite(shares) or shares == 0.0:
            continue
        numerator_metric = next(
            (metric for metric in NUMERATOR_TYPES if period_end in numerators[metric]),
            None,
        )
        if numerator_metric is None:
            continue
        net_income, currency = numerators[numerator_metric][period_end]
        eps = net_income / shares
        if not math.isfinite(eps):
            continue
        rows.append(
            {
                "ticker": ticker,
                "period_end": period_end,
                "report_date": pd.NaT,
                "observed_date": observed_date,
                "metric": DILUTED_METRIC,
                "eps": float(eps),
                "eps_currency": currency,
                "source": f"{SOURCE_PREFIX} ({numerator_metric})",
            }
        )
    return rows


def backfill_component_gaps(*, workers: int = 4) -> pd.DataFrame:
    existing = load_quarterly_eps()
    tickers = _universe()
    observed_date = datetime.now(STOCKHOLM_TZ).date().isoformat()
    rows: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {executor.submit(_fetch_one, ticker, observed_date): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                print(f"VARNING {ticker}: component-backfill misslyckades: {exc}")
            print(f"Yahoo component EPS {index}/{len(tickers)} klar: {ticker}")

    fetched = pd.DataFrame(rows, columns=QUARTERLY_COLUMNS)
    if fetched.empty:
        print("Yahoo component-timeseries: inga diluted EPS-rader kunde härledas.")
        return existing

    fetched["period_end"] = pd.to_datetime(fetched["period_end"], errors="coerce").dt.normalize()
    existing_diluted = existing.loc[existing["metric"].astype(str) == DILUTED_METRIC].copy()
    existing_diluted["period_end"] = pd.to_datetime(existing_diluted["period_end"], errors="coerce").dt.normalize()
    existing_keys = set(zip(existing_diluted["ticker"].astype(str), existing_diluted["period_end"], strict=False))
    fetched = fetched.loc[
        ~fetched.apply(lambda row: (str(row["ticker"]), row["period_end"]) in existing_keys, axis=1)
    ].copy()

    if fetched.empty:
        print("Yahoo component-timeseries: inga nya diluted EPS-luckor att fylla.")
        return existing

    combined = pd.concat([existing, fetched], ignore_index=True)
    save_quarterly_eps(combined)
    saved = load_quarterly_eps()
    _publish_json(saved)
    print(
        f"Yahoo component-timeseries: fyllde {len(fetched)} saknade diluted EPS-perioder "
        f"för {fetched['ticker'].nunique()} tickers."
    )
    return saved


def main() -> None:
    backfill_component_gaps()


if __name__ == "__main__":
    main()
