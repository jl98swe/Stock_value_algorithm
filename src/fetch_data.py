from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

DEFAULT_DATA_FILE = Path(os.getenv("PRICE_DATA_FILE", "data/prices/price_history.parquet"))
DEFAULT_FULL_START = os.getenv("PRICE_HISTORY_START", "2016-01-01")
PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "ticker", "ma200"]


def _normalize_download(downloaded: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Normalisera yfinance-data till projektets gemener + snake_case-schema."""
    frames: list[pd.DataFrame] = []

    for ticker in tickers:
        if isinstance(downloaded.columns, pd.MultiIndex):
            if ticker not in downloaded.columns.get_level_values(0):
                continue
            df = downloaded[ticker].copy()
        else:
            df = downloaded.copy()

        if df.empty or "Close" not in df.columns or not df["Close"].notna().any():
            continue

        # yf.download använder ett gemensamt datumindex för alla tickers.
        # Ta därför bort datum där just denna aktie saknar verklig prisdata.
        df = df.dropna(subset=["Close"]).reset_index()
        df["ticker"] = ticker

        keep = [
            c
            for c in ["Date", "Open", "High", "Low", "Close", "Volume", "ticker"]
            if c in df.columns
        ]
        df = df[keep].rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS[:-1])

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)

    return (
        out.sort_values(["ticker", "date"])
        .drop_duplicates(subset=["ticker", "date"], keep="last")
        .reset_index(drop=True)
    )


def _validate_existing(df: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "open", "high", "low", "close", "volume", "ticker"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Prisfilen saknar kolumner: {', '.join(missing)}")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.dropna(subset=["date", "close", "ticker"])
    df["ticker"] = df["ticker"].astype(str)

    return (
        df.sort_values(["ticker", "date"])
        .drop_duplicates(subset=["ticker", "date"], keep="last")
        .reset_index(drop=True)
    )


def _download(tickers: list[str], *, start: str, end: str) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=PRICE_COLUMNS[:-1])

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
        actions=False,
        timeout=30,
    )
    return _normalize_download(downloaded, tickers)


def _recalculate_ma200(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df["ma200"] = (
        df.groupby("ticker", sort=False)["close"]
        .transform(lambda s: s.rolling(window=200, min_periods=200).mean())
    )
    return df[PRICE_COLUMNS]


def update_prices(data_file: Path = DEFAULT_DATA_FILE, *, full: bool = False) -> pd.DataFrame:
    """
    Uppdatera den permanenta prisfilen.

    Normal körning:
      - läser tickers från den befintliga historikfilen
      - hämtar bara perioden som saknas, med några dagars överlapp
      - merge:ar på ticker + date
      - räknar om MA200 från den kompletta close-serien

    --full:
      - laddar om samtliga tickers från PRICE_HISTORY_START/2016-01-01
    """
    if not data_file.exists():
        raise FileNotFoundError(
            f"Prisfilen finns inte: {data_file}. "
            "Lägg den initiala historikfilen där först."
        )

    existing = _validate_existing(pd.read_parquet(data_file))
    tickers = sorted(existing["ticker"].dropna().unique().tolist())
    if not tickers:
        raise ValueError("Prisfilen innehåller inga tickers.")

    # yfinance behandlar end som exklusivt. I morgon gör att dagens färdiga
    # handelsstapel kan följa med efter kvällskörningen.
    end = (date.today() + timedelta(days=1)).isoformat()

    if full:
        fresh = _download(tickers, start=DEFAULT_FULL_START, end=end)
        if fresh.empty:
            raise RuntimeError("Yahoo returnerade ingen prisdata vid full hämtning.")
        combined = fresh
    else:
        latest = existing.groupby("ticker")["date"].max()

        # De flesta aktier har samma senaste handelsdag. Gruppera efter startdatum
        # så att vi kan hämta många tickers i samma Yahoo-anrop utan 119 separata anrop.
        groups: dict[str, list[str]] = {}
        for ticker in tickers:
            latest_date = latest.loc[ticker].date()
            # Kalenderöverlapp fångar korrigeringar och gör körningen självläkande
            # efter missade helger/handelsdagar. Dubbletter tas bort efteråt.
            start = (latest_date - timedelta(days=7)).isoformat()
            groups.setdefault(start, []).append(ticker)

        new_frames: list[pd.DataFrame] = []
        for start, group_tickers in sorted(groups.items()):
            print(f"Hämtar {len(group_tickers)} ticker från {start} till {end} ...")
            frame = _download(group_tickers, start=start, end=end)
            if not frame.empty:
                new_frames.append(frame)

        if not new_frames:
            print("Ingen ny prisdata hittades. Behåller befintlig historik.")
            combined = existing
        else:
            fresh = pd.concat(new_frames, ignore_index=True)
            combined = pd.concat([existing.drop(columns=["ma200"], errors="ignore"), fresh], ignore_index=True)
            combined = (
                combined.sort_values(["ticker", "date"])
                .drop_duplicates(subset=["ticker", "date"], keep="last")
                .reset_index(drop=True)
            )

    combined = _recalculate_ma200(combined)

    # Enkel OHLC-rimlighetskontroll. Vi stoppar hellre körningen än sparar korrupt data.
    invalid = combined[
        (combined["low"] > combined[["open", "close", "high"]].min(axis=1))
        | (combined["high"] < combined[["open", "close", "low"]].max(axis=1))
        | (combined["close"] <= 0)
    ]
    if not invalid.empty:
        sample = invalid[["date", "ticker", "open", "high", "low", "close"]].head(10)
        raise ValueError(f"Ogiltiga OHLC-rader hittades:\n{sample.to_string(index=False)}")

    data_file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(data_file, index=False)

    latest_after = combined.groupby("ticker")["date"].max()
    print(
        f"Sparade {len(combined):,} rader för {combined['ticker'].nunique()} tickers till {data_file}. "
        f"Senaste datum: {latest_after.max().date()}"
    )
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Uppdatera daglig Yahoo-prisdata och MA200.")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help=f"Parquetfil som ska uppdateras (standard: {DEFAULT_DATA_FILE})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Hämta om hela prisserien från PRICE_HISTORY_START/2016-01-01.",
    )
    args = parser.parse_args()

    update_prices(args.file, full=args.full)


if __name__ == "__main__":
    main()
