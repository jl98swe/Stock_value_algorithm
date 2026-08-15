from __future__ import annotations

import argparse
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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
EARNINGS_COLUMNS = ["ticker", "report_date", "observed_date", "eps_ttm", "source"]
EPS_SOURCE = "Yahoo Finance / trailingEps + get_earnings_dates"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _normalise_earnings(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=EARNINGS_COLUMNS)

    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]

    # Bakåtkompatibilitet med den första versionen av earnings-filerna, som
    # saknade report_date. Nästa skrivning migrerar automatiskt till nya schemat.
    if "report_date" not in result.columns:
        result["report_date"] = pd.NaT

    required = {"ticker", "observed_date", "eps_ttm", "source"}
    missing = sorted(required.difference(result.columns))
    if missing:
        raise ValueError(f"EPS-filen saknar kolumner: {', '.join(missing)}")

    result = result[EARNINGS_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    for column in ("report_date", "observed_date"):
        result[column] = (
            pd.to_datetime(result[column], errors="coerce")
            .dt.tz_localize(None)
            .dt.normalize()
        )
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["source"] = result["source"].astype(str).str.strip()
    result = result.dropna(subset=["ticker", "observed_date", "eps_ttm"])
    result = result.loc[result["ticker"].str.len() > 0]
    return (
        result.sort_values(["ticker", "observed_date"])
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
    try:
        info = yf.Ticker(ticker).get_info()
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo trailingEps kunde inte hämtas: {exc}")
        return None

    value = pd.to_numeric(info.get("trailingEps"), errors="coerce")
    if pd.isna(value) or not math.isfinite(float(value)):
        print(f"INFO {ticker}: Yahoo saknar användbar trailingEps.")
        return None

    return {
        "ticker": ticker,
        "report_date": pd.NaT,
        "observed_date": observed_date,
        "eps_ttm": float(value),
        "source": EPS_SOURCE,
    }


def _select_latest_report_date(
    earnings_dates: pd.DataFrame | None,
    *,
    now: pd.Timestamp | None = None,
) -> pd.Timestamp | None:
    """Välj senaste redan inträffade Yahoo-rapportdatum.

    ``get_earnings_dates`` kan även innehålla framtida estimat. Om kolumnen
    ``Reported EPS`` finns prioriteras rader där faktiskt EPS har rapporterats.
    """
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
        # Vissa Yahoo-symboler saknar Reported EPS trots att rapportdatumet finns.
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
    # Behåll kalenderdatumet som Yahoo anger för rapporthändelsen. Tidszonen
    # behövs inte i den här snapshot-filen; exakt publiceringstid verifieras i
    # reports.csv när värdet ska bli point-in-time-exekverbart.
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
    output = frame.copy()
    if not output.empty:
        for column in ("report_date", "observed_date"):
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
                "report_date": (
                    pd.Timestamp(row.report_date).date().isoformat()
                    if pd.notna(row.report_date)
                    else None
                ),
                "observed_date": pd.Timestamp(row.observed_date).date().isoformat(),
                "eps_ttm": float(row.eps_ttm),
                "source": row.source,
            }
        )
    write_json_atomic(
        EARNINGS_JSON,
        {
            "generated_at": datetime.now(ZoneInfo("Europe/Stockholm")).isoformat(timespec="seconds"),
            "source": EPS_SOURCE,
            "note": "Direkt Yahoo trailing EPS TTM. report_date hämtas från senaste inträffade get_earnings_dates-händelse; observed_date är dagen systemet såg EPS-värdet. Kvartal summeras inte.",
            "latest": rows,
        },
    )


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
        raise RuntimeError("Yahoo returnerade ingen EPS TTM för någon ticker.")

    missing = sorted(set(tickers).difference(set(fetched["ticker"].astype(str))))
    if missing:
        print(f"VARNING: trailingEps saknas för {len(missing)} ticker(s): {', '.join(missing[:20])}")

    # Första lyckade körningen bootstrappar den frysta basfilen. Rapportdatum
    # hämtas endast för rader som faktiskt ska sparas, vilket håller de dagliga
    # Yahoo-anropen små efter initialiseringen.
    if base.empty and old_updates.empty:
        fetched = _attach_report_dates(fetched, workers)
        _write_csv(fetched, base_file)
        _publish_json(fetched)
        print(f"EPS-bas skapad: {len(fetched)} aktuella TTM-värden i {_resolve(base_file)}")
        return fetched

    latest_values: dict[str, float] = {}
    if not history.empty:
        latest = (
            history.sort_values(["ticker", "observed_date"])
            .groupby("ticker", sort=False)
            .tail(1)
        )
        latest_values = {
            str(row.ticker): float(row.eps_ttm)
            for row in latest.itertuples(index=False)
        }

    changed_rows: list[dict[str, object]] = []
    for row in fetched.itertuples(index=False):
        previous = latest_values.get(str(row.ticker))
        if previous is None or not math.isclose(float(row.eps_ttm), previous, rel_tol=1e-12, abs_tol=1e-12):
            changed_rows.append(
                {
                    "ticker": row.ticker,
                    "report_date": pd.NaT,
                    "observed_date": row.observed_date,
                    "eps_ttm": row.eps_ttm,
                    "source": row.source,
                }
            )

    changes = _normalise_earnings(pd.DataFrame(changed_rows, columns=EARNINGS_COLUMNS))
    if not changes.empty:
        changes = _attach_report_dates(changes, workers)
        updates = _normalise_earnings(pd.concat([old_updates, changes], ignore_index=True))
        _write_csv(updates, updates_file)
        print(f"EPS-uppdateringar sparade: {len(changes)} nya/ändrade värden.")
    else:
        print("Ingen EPS TTM har ändrats sedan föregående körning.")

    combined = load_earnings_history(base_file, updates_file)
    _publish_json(combined)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hämta aktuell Yahoo EPS TTM med senaste rapportdatum och spara endast ändrade värden."
    )
    parser.add_argument("--base-file", type=Path, default=BASE_EARNINGS_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_EARNINGS_FILE)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    update_earnings(args.base_file, args.updates_file, workers=args.workers)


if __name__ == "__main__":
    main()
