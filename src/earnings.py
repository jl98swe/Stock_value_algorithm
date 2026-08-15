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
EARNINGS_COLUMNS = ["ticker", "observed_date", "eps_ttm", "source"]
EPS_SOURCE = "Yahoo Finance / trailingEps"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _normalise_earnings(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=EARNINGS_COLUMNS)

    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]
    missing = sorted(set(EARNINGS_COLUMNS).difference(result.columns))
    if missing:
        raise ValueError(f"EPS-filen saknar kolumner: {', '.join(missing)}")

    result = result[EARNINGS_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["observed_date"] = (
        pd.to_datetime(result["observed_date"], errors="coerce")
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


def _fetch_one(ticker: str, observed_date: str) -> dict[str, object] | None:
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
        "observed_date": observed_date,
        "eps_ttm": float(value),
        "source": EPS_SOURCE,
    }


def _fetch_current(tickers: list[str], workers: int) -> pd.DataFrame:
    observed_date = datetime.now(ZoneInfo("Europe/Stockholm")).date().isoformat()
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(_fetch_one, ticker, observed_date): ticker
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
        output["observed_date"] = output["observed_date"].dt.strftime("%Y-%m-%d")
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
            "note": "Direkt Yahoo trailing EPS TTM. Kvartal summeras inte. observed_date är första dag systemet såg värdet, inte rapportens publiceringstid.",
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
    fetched = _fetch_current(tickers, workers)
    if fetched.empty:
        raise RuntimeError("Yahoo returnerade ingen EPS TTM för någon ticker.")

    missing = sorted(set(tickers).difference(set(fetched["ticker"].astype(str))))
    if missing:
        print(f"VARNING: trailingEps saknas för {len(missing)} ticker(s): {', '.join(missing[:20])}")

    # Första lyckade körningen bootstrappar den frysta basfilen. Därefter ändras
    # earnings_initial.csv inte av den dagliga körningen.
    if base.empty and old_updates.empty:
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
                    "observed_date": row.observed_date,
                    "eps_ttm": row.eps_ttm,
                    "source": row.source,
                }
            )

    changes = _normalise_earnings(pd.DataFrame(changed_rows, columns=EARNINGS_COLUMNS))
    if not changes.empty:
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
        description="Hämta direkt aktuell Yahoo EPS TTM och spara endast ändrade värden."
    )
    parser.add_argument("--base-file", type=Path, default=BASE_EARNINGS_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_EARNINGS_FILE)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    update_earnings(args.base_file, args.updates_file, workers=args.workers)


if __name__ == "__main__":
    main()
