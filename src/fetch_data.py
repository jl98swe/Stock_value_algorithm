from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DATA_FILE = Path(os.getenv("PRICE_BASE_FILE", "data/prices/prisdata_initial.parquet"))
UPDATES_FILE = Path(os.getenv("PRICE_UPDATES_FILE", "data/prices/price_updates.csv"))
DEFAULT_FULL_START = os.getenv("PRICE_HISTORY_START", "2016-01-01")
PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "ticker", "ma200"]
RAW_PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "ticker"]


def _normalize_download(downloaded: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
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

        df = df.dropna(subset=["Close"]).reset_index()
        df["ticker"] = ticker
        keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume", "ticker"] if c in df.columns]
        frames.append(
            df[keep].rename(
                columns={
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
        )

    if not frames:
        return pd.DataFrame(columns=RAW_PRICE_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return (
        out.sort_values(["ticker", "date"])
        .drop_duplicates(["ticker", "date"], keep="last")
        .reset_index(drop=True)
    )


def _normalise_stored(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    required = set(RAW_PRICE_COLUMNS)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Prisdata saknar kolumner: {', '.join(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None)
    frame = frame.dropna(subset=["date", "close", "ticker"])
    frame["ticker"] = frame["ticker"].astype(str)
    return frame


def _recalculate_ma200(frame: pd.DataFrame) -> pd.DataFrame:
    frame = (
        frame.sort_values(["ticker", "date"])
        .drop_duplicates(["ticker", "date"], keep="last")
        .reset_index(drop=True)
    )
    frame["ma200"] = (
        frame.groupby("ticker", sort=False)["close"]
        .transform(lambda series: series.rolling(window=200, min_periods=200).mean())
    )
    return frame[PRICE_COLUMNS]


def load_price_history(
    base_file: Path = BASE_DATA_FILE,
    updates_file: Path = UPDATES_FILE,
) -> pd.DataFrame:
    """Läs basfil + dagliga uppdateringar som en sammanhängande prisserie."""
    if not base_file.exists():
        raise FileNotFoundError(f"Initial prisfil saknas: {base_file}")

    base = _normalise_stored(pd.read_parquet(base_file)).drop(columns=["ma200"], errors="ignore")
    frames = [base[RAW_PRICE_COLUMNS]]
    if updates_file.exists() and updates_file.stat().st_size:
        # MA200 i update-filen är ett lagrat resultat för inspektion. Vid läsning
        # räknas det alltid om från hela historiken för att garantera korrekthet.
        updates = _normalise_stored(pd.read_csv(updates_file)).drop(columns=["ma200"], errors="ignore")
        frames.append(updates[RAW_PRICE_COLUMNS])

    return _recalculate_ma200(pd.concat(frames, ignore_index=True))


def _download(tickers: list[str], *, start: str, end: str) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=RAW_PRICE_COLUMNS)
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


def _validate_ohlc(frame: pd.DataFrame) -> None:
    invalid = frame[
        (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["close"] <= 0)
    ]
    if not invalid.empty:
        sample = invalid[["date", "ticker", "open", "high", "low", "close"]].head(10)
        raise ValueError(f"Ogiltiga OHLC-rader hittades:\n{sample.to_string(index=False)}")


def _updates_with_ma200(
    base: pd.DataFrame,
    raw_updates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Kombinera bas + updates, räkna MA200 och returnera båda serierna.

    MA200 måste räknas på hela close-historiken. Därför kan den inte beräknas
    korrekt på endast de nya dagliga raderna.
    """
    combined_raw = pd.concat([base[RAW_PRICE_COLUMNS], raw_updates[RAW_PRICE_COLUMNS]], ignore_index=True)
    combined = _recalculate_ma200(combined_raw)

    base_last = base.groupby("ticker")["date"].max().to_dict()
    update_mask = combined.apply(
        lambda row: row["date"] > base_last.get(row["ticker"], pd.Timestamp.min),
        axis=1,
    )
    updates_with_ma200 = combined.loc[update_mask, PRICE_COLUMNS].reset_index(drop=True)
    return combined, updates_with_ma200


def update_prices(
    base_file: Path = BASE_DATA_FILE,
    updates_file: Path = UPDATES_FILE,
    *,
    full: bool = False,
) -> pd.DataFrame:
    existing = load_price_history(base_file, updates_file)
    tickers = sorted(existing["ticker"].unique().tolist())
    if not tickers:
        raise ValueError("Prisfilen innehåller inga tickers.")

    end = (date.today() + timedelta(days=1)).isoformat()
    if full:
        fresh = _download(tickers, start=DEFAULT_FULL_START, end=end)
    else:
        latest = existing.groupby("ticker")["date"].max()
        groups: dict[str, list[str]] = {}
        for ticker in tickers:
            start = (latest.loc[ticker].date() - timedelta(days=7)).isoformat()
            groups.setdefault(start, []).append(ticker)

        downloaded_frames: list[pd.DataFrame] = []
        for start, group_tickers in sorted(groups.items()):
            print(f"Hämtar {len(group_tickers)} tickers från {start} till {end} ...")
            result = _download(group_tickers, start=start, end=end)
            if not result.empty:
                downloaded_frames.append(result)
        fresh = pd.concat(downloaded_frames, ignore_index=True) if downloaded_frames else pd.DataFrame(columns=RAW_PRICE_COLUMNS)

    # Varje normal körning hämtar sju dagars överlapp. Ett helt tomt svar är
    # därför ett sannolikt hämtfel och ska inte kunna ge en falskt grön Action.
    if fresh.empty:
        raise RuntimeError(
            "Yahoo returnerade ingen prisdata alls. Uppdateringen avbryts så att "
            "GitHub Action inte kan bli falskt grön."
        )

    returned_tickers = set(fresh["ticker"].astype(str).unique())
    missing_tickers = sorted(set(tickers).difference(returned_tickers))
    if missing_tickers:
        print(
            f"VARNING: Yahoo returnerade ingen data för {len(missing_tickers)} ticker(s): "
            + ", ".join(missing_tickers)
        )

    # Validera endast det Yahoo just hämtade. Äldre accepterad historik får inte
    # stoppa dagens uppdatering på grund av historiska Yahoo-reparationer.
    _validate_ohlc(fresh)

    base = _normalise_stored(pd.read_parquet(base_file))[RAW_PRICE_COLUMNS]
    base_last = base.groupby("ticker")["date"].max().to_dict()

    old_updates = pd.DataFrame(columns=RAW_PRICE_COLUMNS)
    if updates_file.exists() and updates_file.stat().st_size:
        old_updates = _normalise_stored(pd.read_csv(updates_file))[RAW_PRICE_COLUMNS]

    keep = fresh.apply(
        lambda row: row["date"] > base_last.get(row["ticker"], pd.Timestamp.min),
        axis=1,
    )
    candidate_updates = fresh.loc[keep, RAW_PRICE_COLUMNS]

    if old_updates.empty:
        raw_updates = candidate_updates.copy()
    elif candidate_updates.empty:
        raw_updates = old_updates.copy()
    else:
        raw_updates = pd.concat([old_updates, candidate_updates], ignore_index=True)

    raw_updates = (
        raw_updates.sort_values(["ticker", "date"])
        .drop_duplicates(["ticker", "date"], keep="last")
        .reset_index(drop=True)
    )

    if raw_updates.empty:
        print("Ingen ny rad att lägga till i price_updates.csv.")
        return existing

    _validate_ohlc(raw_updates)

    # Räkna MA200 på bas + alla dagliga uppdateringar och spara sedan MA200
    # tillsammans med varje update-rad. Detta gör update-filen schema-kompatibel
    # med den historiska prisfilen: date, OHLC, volume, ticker, ma200.
    combined, updates_with_ma200 = _updates_with_ma200(base, raw_updates)

    updates_file.parent.mkdir(parents=True, exist_ok=True)
    updates_with_ma200.to_csv(updates_file, index=False, date_format="%Y-%m-%d")

    print(
        f"Prisdata klar: {len(combined):,} rader, {combined['ticker'].nunique()} tickers, "
        f"senaste datum {combined['date'].max().date()}. "
        f"price_updates.csv innehåller {len(updates_with_ma200):,} rader inklusive MA200."
    )
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Uppdatera Yahoo-priser och MA200.")
    parser.add_argument("--base-file", type=Path, default=BASE_DATA_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_FILE)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    update_prices(args.base_file, args.updates_file, full=args.full)


if __name__ == "__main__":
    main()
