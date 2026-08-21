from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .config import ROOT
from .earnings import latest_earnings
from .fetch_data import load_price_history

OUTPUT_FILE = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
METRICS = [
    "trailingDilutedEPS",
    "trailingBasicEPS",
    "quarterlyDilutedEPS",
    "quarterlyBasicEPS",
]


def _parse_payload(ticker: str, payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for block in (payload.get("timeseries") or {}).get("result") or []:
        for metric in METRICS:
            values = block.get(metric)
            if not isinstance(values, list):
                continue
            for item in values:
                raw = ((item.get("reportedValue") or {}).get("raw"))
                as_of = item.get("asOfDate")
                if raw is None or not as_of:
                    continue
                rows.append(
                    {
                        "ticker": ticker,
                        "metric": metric,
                        "as_of_date": as_of,
                        "value": raw,
                        "currency_code": item.get("currencyCode") or (block.get("meta") or {}).get("currencyCode") or "",
                    }
                )
    return rows


def _fetch_one(ticker: str, period1: int, period2_values: list[int]) -> list[dict[str, object]]:
    """Hämta flera Yahoo-fönster och slå ihop dem.

    Fundamentals-timeseries returnerar ett begränsat antal observationer per
    anrop. Historiska slutdatum gör att annars utelämnade kvartal kan hämtas
    utan någon betaltjänst.
    """
    symbol = yf.Ticker(ticker)
    rows: list[dict[str, object]] = []
    for period2 in period2_values:
        url = (
            f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}"
            f"?symbol={ticker}&type={','.join(METRICS)}&period1={period1}&period2={period2}"
        )
        try:
            response = symbol._data.cache_get(url=url)
            payload = json.loads(response.text)
            rows.extend(_parse_payload(ticker, payload))
        except Exception as exc:
            print(f"VARNING {ticker}: EPS-timeseries-fönster kunde inte hämtas: {exc}")
    return rows


def audit(
    output_file: Path = OUTPUT_FILE,
    *,
    workers: int = 4,
) -> pd.DataFrame:
    """Hämta Yahoo EPS-timeseries för hela prisuniversumet.

    Historikhämtningen är medvetet frikopplad från Börsdata-/referensfilerna.
    Prisuniversumet är källan till vilka aktier som ska hämtas, så nya aktier
    kan få historik direkt från Yahoo utan att först finnas i en köpt fil.

    Vi börjar vid 2022-01-01 och använder täta historiska slutdatum även under
    2022 och första halvåret 2023. Det behövs eftersom Yahoo endast returnerar
    ett begränsat antal fundamentala observationer per anrop. På så sätt kan vi
    faktiskt testa hur tidigt varje ticker har trailingDilutedEPS, i stället
    för att anta att hela universumet börjar samma kvartal.
    """
    prices = load_price_history()
    tickers = sorted(prices["ticker"].dropna().astype(str).str.strip().unique().tolist())
    if not tickers:
        raise ValueError("Prisuniversumet innehåller inga tickers.")

    start = pd.Timestamp("2022-01-01", tz="UTC")
    now = pd.Timestamp(datetime.now(ZoneInfo("Europe/Stockholm")) + timedelta(days=2)).tz_convert("UTC")
    checkpoints = [
        now,
        pd.Timestamp("2026-01-15", tz="UTC"),
        pd.Timestamp("2025-01-15", tz="UTC"),
        pd.Timestamp("2024-08-01", tz="UTC"),
        pd.Timestamp("2024-01-15", tz="UTC"),
        pd.Timestamp("2023-07-15", tz="UTC"),
        pd.Timestamp("2023-04-15", tz="UTC"),
        pd.Timestamp("2023-01-15", tz="UTC"),
        pd.Timestamp("2022-10-15", tz="UTC"),
        pd.Timestamp("2022-07-15", tz="UTC"),
        pd.Timestamp("2022-04-15", tz="UTC"),
    ]
    period1 = int(start.timestamp())
    period2_values = sorted({int(value.timestamp()) for value in checkpoints}, reverse=True)

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {
            executor.submit(_fetch_one, ticker, period1, period2_values): ticker
            for ticker in tickers
        }
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                print(f"VARNING {ticker}: timeseries-audit misslyckades: {exc}")
            print(f"Yahoo EPS-timeseries {index}/{len(tickers)} klar: {ticker}")

    result = pd.DataFrame(rows, columns=["ticker", "metric", "as_of_date", "value", "currency_code"])
    if not result.empty:
        result["as_of_date"] = pd.to_datetime(result["as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        result["value"] = pd.to_numeric(result["value"], errors="coerce")
        result = result.dropna(subset=["as_of_date", "value"])
        result = result.sort_values(["ticker", "metric", "as_of_date"]).drop_duplicates(
            ["ticker", "metric", "as_of_date"], keep="last"
        )

    current = latest_earnings()
    current_map = {
        str(row.ticker): float(row.eps_ttm)
        for row in current.itertuples(index=False)
    } if not current.empty else {}
    if not result.empty:
        result["current_trailing_eps"] = result["ticker"].map(current_map)
        result["is_latest_metric_row"] = False
        latest_indices = result.groupby(["ticker", "metric"])["as_of_date"].idxmax()
        result.loc[latest_indices, "is_latest_metric_row"] = True
    else:
        result["current_trailing_eps"] = pd.Series(dtype=float)
        result["is_latest_metric_row"] = pd.Series(dtype=bool)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)

    covered = result["ticker"].nunique() if not result.empty else 0
    print(f"Yahoo EPS-timeseries: {len(result)} datapunkter för {covered}/{len(tickers)} tickers.")
    if not result.empty:
        counts = result.groupby(["ticker", "metric"]).size().unstack(fill_value=0)
        print("Antal datapunkter per metric, sammanfattning:")
        print(counts.describe().to_string())
    return result


if __name__ == "__main__":
    audit()
