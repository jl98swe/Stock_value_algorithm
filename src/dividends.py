from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yfinance as yf

from .fetch_data import load_price_history


BASE_DIVIDENDS_FILE = Path(
    os.getenv("DIVIDEND_BASE_FILE", "data/dividends/dividends_initial.csv")
)
UPDATES_DIVIDENDS_FILE = Path(
    os.getenv("DIVIDEND_UPDATES_FILE", "data/dividends/dividend_updates.csv")
)
LOOKBACK_PERIOD = os.getenv("DIVIDEND_LOOKBACK_PERIOD", "2y")
DIVIDEND_COLUMNS = ["ticker", "ex_date", "dividend"]


def _normalise_dividends(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]

    missing = sorted(set(DIVIDEND_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"Utdelningsfilen saknar kolumner: {', '.join(missing)}")

    frame = frame[DIVIDEND_COLUMNS]
    frame["ticker"] = frame["ticker"].astype(str)
    frame["ex_date"] = pd.to_datetime(frame["ex_date"], errors="coerce").dt.date.astype("string")
    frame["dividend"] = pd.to_numeric(frame["dividend"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "ex_date", "dividend"])

    return (
        frame.sort_values(["ticker", "ex_date"])
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .reset_index(drop=True)
    )


def _read_dividend_file(path: Path, *, required: bool) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Historisk utdelningsfil saknas: {path}")
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)

    if path.stat().st_size == 0:
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)

    return _normalise_dividends(pd.read_csv(path))


def load_dividend_history(
    base_file: Path = BASE_DIVIDENDS_FILE,
    updates_file: Path = UPDATES_DIVIDENDS_FILE,
) -> pd.DataFrame:
    """Läs fryst utdelningshistorik och små löpande uppdateringar som en serie."""
    base = _read_dividend_file(base_file, required=True)
    updates = _read_dividend_file(updates_file, required=False)

    if updates.empty:
        return base

    return (
        pd.concat([base, updates], ignore_index=True)
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )


def _load_tickers() -> list[str]:
    prices = load_price_history()
    tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())

    if not tickers:
        raise ValueError("Prisdata innehåller inga tickers.")

    return tickers


def _fetch_recent_dividends(tickers: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    errors: list[str] = []

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")

        try:
            dividends = yf.Ticker(ticker).get_dividends(period=LOOKBACK_PERIOD)
        except Exception as exc:
            errors.append(ticker)
            print(f"  Fel: {exc}")
            continue

        for ex_date, amount in dividends.items():
            rows.append(
                {
                    "ticker": ticker,
                    "ex_date": pd.Timestamp(ex_date).date().isoformat(),
                    "dividend": float(amount),
                }
            )

    if errors:
        print(
            f"VARNING: utdelningshämtning misslyckades för {len(errors)} ticker(s): "
            + ", ".join(errors)
        )

    if not rows:
        raise RuntimeError(
            "Yahoo returnerade ingen utdelningsdata alls. Uppdateringen avbryts så att "
            "GitHub Action inte kan bli falskt grön."
        )

    return _normalise_dividends(pd.DataFrame(rows, columns=DIVIDEND_COLUMNS))


def _rows_different_from_base(
    candidates: pd.DataFrame,
    base: pd.DataFrame,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    base_values = {
        (row.ticker, row.ex_date): float(row.dividend)
        for row in base.itertuples(index=False)
    }

    keep = candidates.apply(
        lambda row: (
            (row["ticker"], row["ex_date"]) not in base_values
            or float(row["dividend"])
            != base_values[(row["ticker"], row["ex_date"])]
        ),
        axis=1,
    )
    return candidates.loc[keep, DIVIDEND_COLUMNS].copy()


def update_dividends(
    base_file: Path = BASE_DIVIDENDS_FILE,
    updates_file: Path = UPDATES_DIVIDENDS_FILE,
) -> pd.DataFrame:
    base = _read_dividend_file(base_file, required=True)
    old_updates = _read_dividend_file(updates_file, required=False)
    existing = load_dividend_history(base_file, updates_file)

    tickers = _load_tickers()
    fetched = _fetch_recent_dividends(tickers)

    existing_keys = set(zip(existing["ticker"], existing["ex_date"]))
    new_rows = fetched[
        ~fetched.apply(
            lambda row: (row["ticker"], row["ex_date"]) in existing_keys,
            axis=1,
        )
    ].copy()

    candidate_updates = (
        pd.concat([old_updates, fetched], ignore_index=True)
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )
    updates = _rows_different_from_base(candidate_updates, base)
    updates = (
        updates.sort_values(["ticker", "ex_date"])
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .reset_index(drop=True)
    )

    old_sorted = (
        old_updates.sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )
    changed = not updates.equals(old_sorted)

    if changed:
        updates_file.parent.mkdir(parents=True, exist_ok=True)
        updates.to_csv(updates_file, index=False)

    if not new_rows.empty:
        print(f"Nya utdelningar: {len(new_rows)}")
        print(new_rows.sort_values(["ticker", "ex_date"]).to_string(index=False))
    elif changed:
        print("Ingen ny utdelning, men minst en befintlig post uppdaterades.")
    else:
        print("Ingen ny utdelning.")

    if updates.empty:
        return base

    return (
        pd.concat([base, updates], ignore_index=True)
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    update_dividends()
