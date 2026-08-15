from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import ROOT
from .fetch_data import load_price_history

BASE_DIVIDENDS_FILE = Path(
    os.getenv("DIVIDEND_BASE_FILE", "data/dividends/dividends_initial.csv")
)
UPDATES_DIVIDENDS_FILE = Path(
    os.getenv("DIVIDEND_UPDATES_FILE", "data/dividends/dividend_updates.csv")
)
LOOKBACK_DAYS = int(os.getenv("DIVIDEND_LOOKBACK_DAYS", "365"))
DIVIDEND_COLUMNS = ["ticker", "ex_date", "dividend"]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _normalise_dividends(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)

    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]
    missing = sorted(set(DIVIDEND_COLUMNS).difference(result.columns))
    if missing:
        raise ValueError(f"Utdelningsfilen saknar kolumner: {', '.join(missing)}")

    result = result[DIVIDEND_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["ex_date"] = pd.to_datetime(result["ex_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["dividend"] = pd.to_numeric(result["dividend"], errors="coerce")
    result = result.dropna(subset=["ticker", "ex_date", "dividend"])
    result = result.loc[result["dividend"] > 0]
    return (
        result.sort_values(["ticker", "ex_date"])
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .reset_index(drop=True)
    )


def _read_dividend_file(path: Path, *, required: bool) -> pd.DataFrame:
    target = _resolve(path)
    if not target.exists():
        if required:
            raise FileNotFoundError(f"Historisk utdelningsfil saknas: {target}")
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)
    if target.stat().st_size == 0:
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)
    return _normalise_dividends(pd.read_csv(target))


def load_dividend_history(
    base_file: Path = BASE_DIVIDENDS_FILE,
    updates_file: Path = UPDATES_DIVIDENDS_FILE,
) -> pd.DataFrame:
    """Läs fryst utdelningshistorik och löpande uppdateringar som en serie."""
    base = _read_dividend_file(base_file, required=True)
    updates = _read_dividend_file(updates_file, required=False)
    if updates.empty:
        return base
    return (
        pd.concat([base, updates], ignore_index=True)
        .sort_values(["ticker", "ex_date"])
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .reset_index(drop=True)
    )


def _load_tickers() -> list[str]:
    prices = load_price_history()
    tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())
    if not tickers:
        raise ValueError("Prisdata innehåller inga tickers.")
    return tickers


def _normalise_download(downloaded: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if downloaded is None or downloaded.empty:
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)

    rows: list[dict[str, object]] = []
    for ticker in tickers:
        if isinstance(downloaded.columns, pd.MultiIndex):
            if ticker not in downloaded.columns.get_level_values(0):
                continue
            frame = downloaded[ticker]
        else:
            frame = downloaded

        if "Dividends" not in frame.columns:
            continue
        values = pd.to_numeric(frame["Dividends"], errors="coerce").fillna(0.0)
        for timestamp, amount in values.loc[values > 0].items():
            rows.append(
                {
                    "ticker": ticker,
                    "ex_date": pd.Timestamp(timestamp).tz_localize(None).normalize(),
                    "dividend": float(amount),
                }
            )

    return _normalise_dividends(pd.DataFrame(rows, columns=DIVIDEND_COLUMNS))


def _fetch_recent_dividends(tickers: list[str]) -> pd.DataFrame:
    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = (date.today() + timedelta(days=1)).isoformat()
    downloaded = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        repair=True,
        group_by="ticker",
        threads=True,
        progress=False,
        actions=True,
        timeout=30,
    )
    return _normalise_download(downloaded, tickers)


def _rows_different_from_base(candidates: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    base_values = {
        (row.ticker, row.ex_date): float(row.dividend)
        for row in base.itertuples(index=False)
    }
    keep: list[bool] = []
    for row in candidates.itertuples(index=False):
        old_value = base_values.get((row.ticker, row.ex_date))
        keep.append(old_value is None or abs(float(row.dividend) - old_value) > 1e-10)
    return candidates.loc[keep, DIVIDEND_COLUMNS].copy()


def update_dividends(
    base_file: Path = BASE_DIVIDENDS_FILE,
    updates_file: Path = UPDATES_DIVIDENDS_FILE,
) -> pd.DataFrame:
    """Uppdatera utdelningar utan att skriva om den frysta historikfilen."""
    base = _read_dividend_file(base_file, required=True)
    old_updates = _read_dividend_file(updates_file, required=False)
    tickers = _load_tickers()
    fetched = _fetch_recent_dividends(tickers)

    # Ett tomt utdelningsresultat är inte automatiskt ett fel: det kan helt enkelt
    # saknas ex-dagar i det senaste fönstret. Prisuppdateringen validerar separat
    # att Yahoo faktiskt svarar.
    if fetched.empty:
        print("Ingen utdelning hittades i det senaste Yahoo-fönstret.")
        return load_dividend_history(base_file, updates_file)

    candidates = _rows_different_from_base(fetched, base)
    if old_updates.empty:
        updates = candidates.copy()
    elif candidates.empty:
        updates = old_updates.copy()
    else:
        updates = pd.concat([old_updates, candidates], ignore_index=True)
    updates = _normalise_dividends(updates)

    old_sorted = _normalise_dividends(old_updates)
    changed = not updates.equals(old_sorted)
    if changed:
        target = _resolve(updates_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        output = updates.copy()
        output["ex_date"] = output["ex_date"].dt.strftime("%Y-%m-%d")
        output.to_csv(target, index=False)
        print(f"Utdelningsuppdateringar sparade: {len(updates):,} poster.")
    else:
        print("Ingen ny eller korrigerad utdelning.")

    return load_dividend_history(base_file, updates_file)


if __name__ == "__main__":
    update_dividends()
