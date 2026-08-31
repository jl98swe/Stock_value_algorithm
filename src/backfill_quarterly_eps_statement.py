from __future__ import annotations

import argparse
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .fetch_data import load_price_history
from .quarterly_eps import (
    DILUTED_METRIC,
    QUARTERLY_COLUMNS,
    _metadata_currency_map,
    _publish_json,
    load_quarterly_eps,
    save_quarterly_eps,
)

DIRECT_SOURCE = "Yahoo Finance / quarterly_income_stmt DilutedEPS"
RATIO_SOURCE = "Yahoo Finance / quarterly_income_stmt diluted net income / diluted average shares"
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
STALE_DAYS = 115
NUMERATOR_CANDIDATES = (
    "DilutedNIAvailtoComStockholders",
    "NetIncomeCommonStockholders",
)
DENOMINATOR_CANDIDATES = (
    "DilutedAverageShares",
)


def _ticker_universe() -> list[str]:
    prices = load_price_history()
    return sorted(prices["ticker"].dropna().astype(str).str.strip().unique().tolist())


def _statement_series(statement: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series | None:
    row_name = next((name for name in candidates if name in statement.index), None)
    if row_name is None:
        return None
    series = statement.loc[row_name]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[0]
    return pd.to_numeric(series, errors="coerce")


def _extract_diluted_eps(ticker: str, observed_date: str, currency: str) -> list[dict[str, object]]:
    try:
        statement = yf.Ticker(ticker).get_income_stmt(freq="quarterly", pretty=False)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo quarterly income statement kunde inte hämtas: {exc}")
        return []
    if statement is None or statement.empty:
        return []

    direct = _statement_series(statement, ("DilutedEPS", "Diluted EPS"))
    numerator = _statement_series(statement, NUMERATOR_CANDIDATES)
    denominator = _statement_series(statement, DENOMINATOR_CANDIDATES)

    periods = list(statement.columns)
    rows: list[dict[str, object]] = []
    for period_end in periods:
        period = pd.to_datetime(period_end, errors="coerce")
        if pd.isna(period):
            continue

        eps: float | None = None
        source = ""
        if direct is not None and period_end in direct.index:
            value = pd.to_numeric(direct.get(period_end), errors="coerce")
            if pd.notna(value) and math.isfinite(float(value)):
                eps = float(value)
                source = DIRECT_SOURCE

        if eps is None and numerator is not None and denominator is not None:
            net_income = pd.to_numeric(numerator.get(period_end), errors="coerce")
            diluted_shares = pd.to_numeric(denominator.get(period_end), errors="coerce")
            if (
                pd.notna(net_income)
                and pd.notna(diluted_shares)
                and math.isfinite(float(net_income))
                and math.isfinite(float(diluted_shares))
                and float(diluted_shares) != 0.0
            ):
                value = float(net_income) / float(diluted_shares)
                if math.isfinite(value):
                    eps = value
                    source = RATIO_SOURCE

        if eps is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "period_end": pd.Timestamp(period).tz_localize(None).normalize(),
                "report_date": pd.NaT,
                "observed_date": observed_date,
                "metric": DILUTED_METRIC,
                "eps": float(eps),
                "eps_currency": currency,
                "source": source,
            }
        )
    return rows


def _needs_refresh(ticker: str, existing: pd.DataFrame, today: pd.Timestamp) -> bool:
    subset = existing.loc[
        (existing["ticker"].astype(str) == ticker)
        & (existing["metric"].astype(str) == DILUTED_METRIC)
    ]
    if subset.empty:
        return True
    latest = pd.to_datetime(subset["period_end"], errors="coerce").dropna().max()
    if pd.isna(latest):
        return True
    return int((today.normalize() - pd.Timestamp(latest).normalize()).days) >= STALE_DAYS


def backfill_statement_gaps(*, workers: int = 4, stale_only: bool = False) -> pd.DataFrame:
    existing = load_quarterly_eps()
    tickers = _ticker_universe()
    if not tickers:
        raise ValueError("Prisuniversumet innehåller inga tickers.")

    today = pd.Timestamp(datetime.now(STOCKHOLM_TZ).date())
    observed_date = today.date().isoformat()
    currency_map = _metadata_currency_map()
    selected = [ticker for ticker in tickers if not stale_only or _needs_refresh(ticker, existing, today)]
    if not selected:
        print("Yahoo income-statement fallback: inga tickers behöver uppdateras.")
        return existing

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(selected)))) as executor:
        futures = {
            executor.submit(
                _extract_diluted_eps,
                ticker,
                observed_date,
                currency_map.get(ticker, ""),
            ): ticker
            for ticker in selected
        }
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                print(f"VARNING {ticker}: statement-fallback misslyckades: {exc}")
            print(f"Yahoo statement EPS {index}/{len(selected)} klar: {ticker}")

    fetched = pd.DataFrame(rows, columns=QUARTERLY_COLUMNS)
    if fetched.empty:
        print("Yahoo income-statement fallback: inga diluted EPS-komponenter returnerades.")
        return existing

    existing_keys = set(
        zip(
            existing.loc[existing["metric"] == DILUTED_METRIC, "ticker"].astype(str),
            pd.to_datetime(
                existing.loc[existing["metric"] == DILUTED_METRIC, "period_end"],
                errors="coerce",
            ).dt.normalize(),
            strict=False,
        )
    )
    fetched["period_end"] = pd.to_datetime(fetched["period_end"], errors="coerce").dt.normalize()
    fetched = fetched.loc[
        ~fetched.apply(lambda row: (str(row["ticker"]), row["period_end"]) in existing_keys, axis=1)
    ].copy()

    if fetched.empty:
        print("Yahoo income-statement fallback: inga nya luckor att fylla.")
        return existing

    combined = pd.concat([existing, fetched], ignore_index=True)
    save_quarterly_eps(combined)
    saved = load_quarterly_eps()
    _publish_json(saved)
    direct_count = int((fetched["source"] == DIRECT_SOURCE).sum())
    ratio_count = int((fetched["source"] == RATIO_SOURCE).sum())
    print(
        f"Yahoo income-statement fallback: fyllde {len(fetched)} saknade diluted EPS-perioder "
        f"för {fetched['ticker'].nunique()} tickers ({direct_count} direkt, {ratio_count} från nettoresultat/utspädda aktier)."
    )
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fyll luckor i Yahoo quarterlyDilutedEPS från Yahoos kvartalsvisa resultaträkning."
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--stale-only",
        action="store_true",
        help=f"Hämta bara tickers vars senaste diluted EPS är minst {STALE_DAYS} dagar gammal.",
    )
    args = parser.parse_args()
    backfill_statement_gaps(workers=args.workers, stale_only=args.stale_only)


if __name__ == "__main__":
    main()
