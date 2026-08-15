from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .config import ROOT
from .fetch_data import load_price_history
from .utils import write_json_atomic

BASE_EARNINGS_FILE = Path("data/earnings/earnings_initial.csv")
UPDATES_EARNINGS_FILE = Path("data/earnings/earnings_updates.csv")
EARNINGS_JSON = ROOT / "docs" / "data" / "earnings.json"
EARNINGS_COLUMNS = [
    "ticker",
    "period_end",
    "report_date",
    "observed_date",
    "eps_ttm",
    "eps_currency",
    "source",
]
EPS_METRIC = "trailingDilutedEPS"
EPS_SOURCE = "Yahoo Finance / trailingDilutedEPS"
LEGACY_SOURCE_TOKEN = "trailingEps"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _normalise_earnings(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=EARNINGS_COLUMNS)

    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]

    # Bakåtkompatibilitet med äldre snapshot-filer. De migreras till
    # trailingDilutedEPS vid nästa lyckade update_earnings-körning.
    if "period_end" not in result.columns:
        result["period_end"] = pd.NaT
    if "report_date" not in result.columns:
        result["report_date"] = pd.NaT
    if "eps_currency" not in result.columns:
        result["eps_currency"] = ""

    required = {"ticker", "observed_date", "eps_ttm", "source"}
    missing = sorted(required.difference(result.columns))
    if missing:
        raise ValueError(f"EPS-filen saknar kolumner: {', '.join(missing)}")

    result = result[EARNINGS_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    for column in ("period_end", "report_date", "observed_date"):
        result[column] = (
            pd.to_datetime(result[column], errors="coerce")
            .dt.tz_localize(None)
            .dt.normalize()
        )
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["eps_currency"] = result["eps_currency"].fillna("").astype(str).str.strip().str.upper()
    result["source"] = result["source"].astype(str).str.strip()
    result = result.dropna(subset=["ticker", "observed_date", "eps_ttm"])
    result = result.loc[result["ticker"].str.len() > 0]
    return (
        result.sort_values(["ticker", "observed_date", "period_end"], na_position="last")
        .drop_duplicates(["ticker", "observed_date"], keep="last")
        .reset_index(drop=True)
    )


def _read_earnings_file(path: Path) -> pd.DataFrame:
    target = _resolve(path)
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=EARNINGS_COLUMNS)
    return _normalise_earnings(pd.read_csv(target))


def load_earnings_history(
    base_file: Path = BASE_EARNINGS_FILE,
    updates_file: Path = UPDATES_EARNINGS_FILE,
) -> pd.DataFrame:
    """Läs fryst EPS-bas och löpande ändringar som en sammanhängande serie."""
    base = _read_earnings_file(base_file)
    updates = _read_earnings_file(updates_file)
    if base.empty:
        return updates
    if updates.empty:
        return base
    return _normalise_earnings(pd.concat([base, updates], ignore_index=True))


def latest_earnings(
    base_file: Path = BASE_EARNINGS_FILE,
    updates_file: Path = UPDATES_EARNINGS_FILE,
) -> pd.DataFrame:
    history = load_earnings_history(base_file, updates_file)
    if history.empty:
        return history
    return (
        history.sort_values(["ticker", "observed_date"])
        .groupby("ticker", as_index=False, sort=True)
        .tail(1)
        .sort_values("ticker")
        .reset_index(drop=True)
    )


def _fetch_eps_one(ticker: str, observed_date: str) -> dict[str, object] | None:
    """Hämta senaste Yahoo trailingDilutedEPS i dess rapportvaluta.

    Detta är samma Yahoo-metric som används för den alignade historiken. Till
    skillnad från quoteSummary-fältet trailingEps ger fundamentals-timeseries
    även period_end och currencyCode, vilket gör historik och framtid direkt
    jämförbara innan projektets separata FX-konvertering.
    """
    now = datetime.now(ZoneInfo("Europe/Stockholm"))
    period1 = int((now - timedelta(days=1000)).timestamp())
    period2 = int((now + timedelta(days=2)).timestamp())
    symbol = yf.Ticker(ticker)
    url = (
        f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}"
        f"?symbol={ticker}&type={EPS_METRIC}&period1={period1}&period2={period2}"
    )
    try:
        response = symbol._data.cache_get(url=url)
        payload = json.loads(response.text)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo {EPS_METRIC} kunde inte hämtas: {exc}")
        return None

    candidates: list[tuple[pd.Timestamp, float, str]] = []
    for block in (payload.get("timeseries") or {}).get("result") or []:
        values = block.get(EPS_METRIC)
        if not isinstance(values, list):
            continue
        block_currency = str((block.get("meta") or {}).get("currencyCode") or "").strip().upper()
        for item in values:
            raw = pd.to_numeric((item.get("reportedValue") or {}).get("raw"), errors="coerce")
            period_end = pd.to_datetime(item.get("asOfDate"), errors="coerce")
            if pd.isna(raw) or pd.isna(period_end) or not math.isfinite(float(raw)):
                continue
            currency = str(item.get("currencyCode") or block_currency or "").strip().upper()
            if not currency:
                continue
            candidates.append((pd.Timestamp(period_end).tz_localize(None).normalize(), float(raw), currency))

    if not candidates:
        print(f"INFO {ticker}: Yahoo saknar användbar {EPS_METRIC}.")
        return None

    period_end, value, currency = max(candidates, key=lambda item: item[0])
    return {
        "ticker": ticker,
        "period_end": period_end,
        "report_date": pd.NaT,
        "observed_date": observed_date,
        "eps_ttm": value,
        "eps_currency": currency,
        "source": EPS_SOURCE,
    }


def _select_latest_report_date(
    earnings_dates: pd.DataFrame | None,
    *,
    now: pd.Timestamp | None = None,
) -> pd.Timestamp | None:
    """Välj senaste redan inträffade Yahoo-rapportdatum."""
    if earnings_dates is None or earnings_dates.empty:
        return None

    current = now if now is not None else pd.Timestamp.now(tz="UTC")
    current = pd.Timestamp(current)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")

    candidates: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for index, row in earnings_dates.iterrows():
        timestamp = pd.to_datetime(index, errors="coerce")
        if pd.isna(timestamp):
            continue
        timestamp = pd.Timestamp(timestamp)
        comparison = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        if comparison > current:
            continue
        if "Reported EPS" in earnings_dates.columns and pd.isna(row.get("Reported EPS")):
            continue
        candidates.append((comparison, timestamp))

    if not candidates and "Reported EPS" in earnings_dates.columns:
        for index in earnings_dates.index:
            timestamp = pd.to_datetime(index, errors="coerce")
            if pd.isna(timestamp):
                continue
            timestamp = pd.Timestamp(timestamp)
            comparison = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
            if comparison <= current:
                candidates.append((comparison, timestamp))

    if not candidates:
        return None

    _, latest = max(candidates, key=lambda item: item[0])
    return pd.Timestamp(latest.date())


def _fetch_report_date_one(ticker: str) -> pd.Timestamp | None:
    try:
        dates = yf.Ticker(ticker).get_earnings_dates(limit=12, offset=1)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo rapportdatum kunde inte hämtas: {exc}")
        return None
    report_date = _select_latest_report_date(dates)
    if report_date is None:
        print(f"INFO {ticker}: inget tidigare Yahoo-rapportdatum hittades.")
    return report_date


def _attach_report_dates(frame: pd.DataFrame, workers: int) -> pd.DataFrame:
    if frame.empty:
        return _normalise_earnings(frame)

    result = frame.copy()
    tickers = result["ticker"].astype(str).unique().tolist()
    report_dates: dict[str, pd.Timestamp | None] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {executor.submit(_fetch_report_date_one, ticker): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                report_dates[ticker] = future.result()
            except Exception as exc:
                print(f"VARNING {ticker}: rapportdatumshämtningen misslyckades: {exc}")
                report_dates[ticker] = None
            print(f"Rapportdatum {index}/{len(tickers)} klar: {ticker}")

    result["report_date"] = result["ticker"].map(report_dates)
    missing = int(result["report_date"].isna().sum())
    if missing:
        print(f"VARNING: {missing} EPS-rad(er) saknar Yahoo-rapportdatum och sparas med tomt report_date.")
    return _normalise_earnings(result)


def _fetch_current_eps(tickers: list[str], workers: int) -> pd.DataFrame:
    observed_date = datetime.now(ZoneInfo("Europe/Stockholm")).date().isoformat()
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(_fetch_eps_one, ticker, observed_date): ticker
            for ticker in tickers
        }
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                print(f"VARNING {ticker}: EPS-hämtningen misslyckades: {exc}")
                row = None
            if row is not None:
                rows.append(row)
            print(f"EPS TTM {index}/{len(tickers)} klar: {ticker}")

    return _normalise_earnings(pd.DataFrame(rows, columns=EARNINGS_COLUMNS))


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    output = _normalise_earnings(frame).copy()
    for column in ("period_end", "report_date", "observed_date"):
        output[column] = output[column].dt.strftime("%Y-%m-%d")
    output.to_csv(target, index=False)


def _publish_json(history: pd.DataFrame) -> None:
    latest = (
        history.sort_values(["ticker", "observed_date"])
        .groupby("ticker", as_index=False, sort=True)
        .tail(1)
        .sort_values("ticker")
        .reset_index(drop=True)
        if not history.empty
        else history
    )
    rows: list[dict[str, object]] = []
    for row in latest.itertuples(index=False):
        rows.append(
            {
                "ticker": row.ticker,
                "period_end": pd.Timestamp(row.period_end).date().isoformat() if pd.notna(row.period_end) else None,
                "report_date": pd.Timestamp(row.report_date).date().isoformat() if pd.notna(row.report_date) else None,
                "observed_date": pd.Timestamp(row.observed_date).date().isoformat(),
                "eps_ttm": float(row.eps_ttm),
                "eps_currency": row.eps_currency or None,
                "source": row.source,
            }
        )
    write_json_atomic(
        EARNINGS_JSON,
        {
            "generated_at": datetime.now(ZoneInfo("Europe/Stockholm")).isoformat(timespec="seconds"),
            "source": EPS_SOURCE,
            "metric": EPS_METRIC,
            "note": (
                "Yahoo trailingDilutedEPS hämtas direkt från fundamentals-timeseries i den valuta Yahoo anger för EPS. "
                "Det är samma metric som används för den alignade historiken. report_date kommer från senaste "
                "inträffade get_earnings_dates-händelse; observed_date är dagen systemet först såg perioden/värdet."
            ),
            "latest": rows,
        },
    )


def _is_current_metric(history: pd.DataFrame) -> bool:
    if history.empty:
        return False
    sources = history["source"].fillna("").astype(str)
    return bool((sources == EPS_SOURCE).all() and history["eps_currency"].astype(str).str.len().gt(0).all())


def _signature(row: pd.Series | object) -> tuple[str, float, str]:
    period_end = getattr(row, "period_end", pd.NaT)
    eps_ttm = getattr(row, "eps_ttm", math.nan)
    currency = getattr(row, "eps_currency", "")
    period_text = pd.Timestamp(period_end).date().isoformat() if pd.notna(period_end) else ""
    return period_text, float(eps_ttm), str(currency or "").upper()


def update_earnings(
    base_file: Path = BASE_EARNINGS_FILE,
    updates_file: Path = UPDATES_EARNINGS_FILE,
    *,
    workers: int = 4,
) -> pd.DataFrame:
    prices = load_price_history()
    tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())
    if not tickers:
        raise ValueError("Prisdata innehåller inga tickers.")

    base = _read_earnings_file(base_file)
    old_updates = _read_earnings_file(updates_file)
    history = load_earnings_history(base_file, updates_file)
    fetched = _fetch_current_eps(tickers, workers)
    if fetched.empty:
        raise RuntimeError(f"Yahoo returnerade ingen {EPS_METRIC} för någon ticker.")

    missing = sorted(set(tickers).difference(set(fetched["ticker"].astype(str))))
    if missing:
        print(f"VARNING: {EPS_METRIC} saknas för {len(missing)} ticker(s): {', '.join(missing[:20])}")

    # Första körningen efter metricbytet migrerar bort gamla quoteSummary-
    # trailingEps snapshots. Vi blandar aldrig två EPS-definitioner i samma
    # tidsserie.
    metric_migration = (not history.empty) and not _is_current_metric(history)
    if (base.empty and old_updates.empty) or metric_migration:
        fetched = _attach_report_dates(fetched, workers)
        _write_csv(fetched, base_file)
        _write_csv(pd.DataFrame(columns=EARNINGS_COLUMNS), updates_file)
        _publish_json(fetched)
        action = "migrerad till" if metric_migration else "skapad med"
        print(
            f"EPS-bas {action} Yahoo {EPS_METRIC}: {len(fetched)} aktuella värden i {_resolve(base_file)}. "
            "Äldre trailingEps-snapshots blandas inte med den nya serien."
        )
        return fetched

    latest_rows: dict[str, object] = {}
    if not history.empty:
        latest = history.sort_values(["ticker", "observed_date"]).groupby("ticker", sort=False).tail(1)
        latest_rows = {str(row.ticker): row for row in latest.itertuples(index=False)}

    changed_rows: list[dict[str, object]] = []
    for row in fetched.itertuples(index=False):
        previous = latest_rows.get(str(row.ticker))
        changed = previous is None
        if previous is not None:
            old_period, old_value, old_currency = _signature(previous)
            new_period, new_value, new_currency = _signature(row)
            changed = (
                old_period != new_period
                or old_currency != new_currency
                or not math.isclose(new_value, old_value, rel_tol=1e-12, abs_tol=1e-12)
            )
        if changed:
            changed_rows.append(
                {
                    "ticker": row.ticker,
                    "period_end": row.period_end,
                    "report_date": pd.NaT,
                    "observed_date": row.observed_date,
                    "eps_ttm": row.eps_ttm,
                    "eps_currency": row.eps_currency,
                    "source": row.source,
                }
            )

    changes = _normalise_earnings(pd.DataFrame(changed_rows, columns=EARNINGS_COLUMNS))
    if not changes.empty:
        changes = _attach_report_dates(changes, workers)
        updates = _normalise_earnings(pd.concat([old_updates, changes], ignore_index=True))
        _write_csv(updates, updates_file)
        print(f"EPS-uppdateringar sparade: {len(changes)} nya/ändrade perioder eller värden.")
    else:
        print(f"Ingen Yahoo {EPS_METRIC} har ändrats sedan föregående körning.")

    combined = load_earnings_history(base_file, updates_file)
    _publish_json(combined)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Hämta aktuell Yahoo trailingDilutedEPS i rapportvaluta med periodslut/rapportdatum och spara endast ändringar."
        )
    )
    parser.add_argument("--base-file", type=Path, default=BASE_EARNINGS_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_EARNINGS_FILE)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    update_earnings(args.base_file, args.updates_file, workers=args.workers)


if __name__ == "__main__":
    main()
