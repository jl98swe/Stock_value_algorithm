from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yfinance as yf

from fetch_data import load_price_history


DIVIDENDS_FILE = Path(os.getenv("DIVIDENDS_FILE", "data/dividends.csv"))
DIVIDEND_COLUMNS = ["ticker", "ex_date", "dividend"]


def _load_dividends(path: Path = DIVIDENDS_FILE) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Historisk utdelningsfil saknas: {path}. Lägg in dividends.csv först."
        )

    frame = pd.read_csv(path, dtype={"ticker": str, "ex_date": str})
    missing = sorted(set(DIVIDEND_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"Utdelningsfilen saknar kolumner: {', '.join(missing)}")

    frame = frame[DIVIDEND_COLUMNS].copy()
    frame["dividend"] = pd.to_numeric(frame["dividend"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "ex_date", "dividend"])

    return (
        frame.sort_values(["ticker", "ex_date"])
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .reset_index(drop=True)
    )


def _load_tickers() -> list[str]:
    prices = load_price_history()
    tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())

    if not tickers:
        raise ValueError("Prisdata innehåller inga tickers.")

    return tickers


def _fetch_dividends(tickers: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    errors: list[str] = []

    for index, ticker in enumerate(tickers, start=1):
        print(f"[{index}/{len(tickers)}] {ticker}")

        try:
            dividends = yf.Ticker(ticker).get_dividends(period="max")
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
        return pd.DataFrame(columns=DIVIDEND_COLUMNS)

    return (
        pd.DataFrame(rows, columns=DIVIDEND_COLUMNS)
        .sort_values(["ticker", "ex_date"])
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .reset_index(drop=True)
    )


def update_dividends(path: Path = DIVIDENDS_FILE) -> pd.DataFrame:
    old = _load_dividends(path)
    tickers = _load_tickers()
    fetched = _fetch_dividends(tickers)

    if fetched.empty:
        print("Ingen utdelningsdata hämtades. Befintlig fil lämnas oförändrad.")
        return old

    old_keys = set(zip(old["ticker"], old["ex_date"]))
    new_rows = fetched[
        ~fetched.apply(
            lambda row: (row["ticker"], row["ex_date"]) in old_keys,
            axis=1,
        )
    ].copy()

    combined = (
        pd.concat([old, fetched], ignore_index=True)
        .drop_duplicates(["ticker", "ex_date"], keep="last")
        .sort_values(["ticker", "ex_date"])
        .reset_index(drop=True)
    )

    changed = not combined.equals(old)

    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(path, index=False)

    if not new_rows.empty:
        print(f"Nya utdelningar: {len(new_rows)}")
        print(new_rows.sort_values(["ticker", "ex_date"]).to_string(index=False))
    elif changed:
        print("Ingen ny utdelning, men minst en befintlig post uppdaterades.")
    else:
        print("Ingen ny utdelning.")

    return combined


if __name__ == "__main__":
    update_dividends()
