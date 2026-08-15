from __future__ import annotations

import argparse
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import ROOT

FX_BASE_FILE = Path("data/fx/fx_initial.csv")
FX_UPDATES_FILE = Path("data/fx/fx_updates.csv")
STOCK_METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
DEFAULT_FX_START = "2016-01-01"
FX_COLUMNS = ["date", "base_currency", "quote_currency", "rate", "yahoo_ticker"]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _normalise_fx(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=FX_COLUMNS)

    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]
    missing = [column for column in FX_COLUMNS if column not in result.columns]
    if missing:
        raise ValueError(f"FX-data saknar kolumner: {', '.join(missing)}")

    result = result[FX_COLUMNS].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["base_currency"] = result["base_currency"].astype(str).str.strip().str.upper()
    result["quote_currency"] = result["quote_currency"].astype(str).str.strip().str.upper()
    result["rate"] = pd.to_numeric(result["rate"], errors="coerce")
    result["yahoo_ticker"] = result["yahoo_ticker"].astype(str).str.strip()
    result = result.dropna(subset=["date", "rate"])
    result = result.loc[
        (result["base_currency"].str.len() == 3)
        & (result["quote_currency"].str.len() == 3)
        & result["rate"].map(lambda value: math.isfinite(float(value)) and float(value) > 0)
    ]
    return (
        result.sort_values(["base_currency", "quote_currency", "date"])
        .drop_duplicates(["base_currency", "quote_currency", "date"], keep="last")
        .reset_index(drop=True)
    )


def _read_fx_file(path: Path) -> pd.DataFrame:
    target = _resolve(path)
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=FX_COLUMNS)
    return _normalise_fx(pd.read_csv(target))


def load_fx_history(
    base_file: Path = FX_BASE_FILE,
    updates_file: Path = FX_UPDATES_FILE,
) -> pd.DataFrame:
    base = _read_fx_file(base_file)
    updates = _read_fx_file(updates_file)
    if base.empty:
        return updates
    if updates.empty:
        return base
    return _normalise_fx(pd.concat([base, updates], ignore_index=True))


def load_stock_currencies(path: Path = STOCK_METADATA_FILE) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["ticker", "price_currency", "report_currency"])
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = ["ticker", "price_currency", "report_currency"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"stocks_yahoo.csv saknar kolumner: {', '.join(missing)}")
    result = frame[required].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    for column in ("price_currency", "report_currency"):
        result[column] = result[column].astype(str).str.strip().str.upper()
    return result.drop_duplicates("ticker", keep="last").reset_index(drop=True)


def required_currency_pairs(metadata: pd.DataFrame | None = None) -> list[tuple[str, str]]:
    frame = load_stock_currencies() if metadata is None else metadata.copy()
    if frame.empty:
        return []
    pairs = {
        (str(row.report_currency).upper(), str(row.price_currency).upper())
        for row in frame.itertuples(index=False)
        if str(row.report_currency).strip()
        and str(row.price_currency).strip()
        and str(row.report_currency).upper() != str(row.price_currency).upper()
    }
    return sorted(pairs)


def yahoo_fx_ticker(base_currency: str, quote_currency: str) -> str:
    base = str(base_currency).strip().upper()
    quote = str(quote_currency).strip().upper()
    if len(base) != 3 or len(quote) != 3:
        raise ValueError(f"Ogiltigt valutapar: {base_currency}/{quote_currency}")
    return f"{base}{quote}=X"


def _download_pair(
    base_currency: str,
    quote_currency: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    symbol = yahoo_fx_ticker(base_currency, quote_currency)
    downloaded = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=False,
        repair=True,
        progress=False,
        threads=False,
        group_by="ticker",
    )
    if downloaded is None or downloaded.empty:
        return pd.DataFrame(columns=FX_COLUMNS)

    frame = downloaded.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        level0 = frame.columns.get_level_values(0)
        if symbol in level0:
            frame = frame[symbol].copy()
        elif "Close" in level0:
            close = frame["Close"].copy()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            frame = pd.DataFrame({"Close": close}, index=downloaded.index)

    if "Close" not in frame.columns:
        return pd.DataFrame(columns=FX_COLUMNS)

    frame = frame.reset_index()
    date_column = "Date" if "Date" in frame.columns else frame.columns[0]
    result = pd.DataFrame(
        {
            "date": frame[date_column],
            "base_currency": str(base_currency).upper(),
            "quote_currency": str(quote_currency).upper(),
            "rate": frame["Close"],
            "yahoo_ticker": symbol,
        }
    )
    return _normalise_fx(result)


def _write_fx(frame: pd.DataFrame, path: Path) -> None:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    output = _normalise_fx(frame).copy()
    if not output.empty:
        output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    output.to_csv(target, index=False)


def update_fx(
    base_file: Path = FX_BASE_FILE,
    updates_file: Path = FX_UPDATES_FILE,
    *,
    full_start: str = DEFAULT_FX_START,
) -> pd.DataFrame:
    metadata = load_stock_currencies()
    pairs = required_currency_pairs(metadata)
    if not pairs:
        print("Ingen valutaomräkning krävs för nuvarande metadata.")
        return load_fx_history(base_file, updates_file)

    base = _read_fx_file(base_file)
    old_updates = _read_fx_file(updates_file)
    history = load_fx_history(base_file, updates_file)
    end = (date.today() + timedelta(days=2)).isoformat()

    fetched_parts: list[pd.DataFrame] = []
    for base_currency, quote_currency in pairs:
        pair_history = history.loc[
            (history["base_currency"] == base_currency)
            & (history["quote_currency"] == quote_currency)
        ]
        if pair_history.empty:
            start = full_start
        else:
            start = (pair_history["date"].max().date() - timedelta(days=10)).isoformat()

        print(f"Hämtar FX {base_currency}/{quote_currency} från {start} ...")
        fresh = _download_pair(base_currency, quote_currency, start, end)
        if fresh.empty:
            if pair_history.empty:
                raise RuntimeError(f"Yahoo returnerade ingen FX-data för {base_currency}/{quote_currency}")
            print(f"VARNING: ingen ny FX-data för {base_currency}/{quote_currency}; befintlig historik behålls.")
            continue
        fetched_parts.append(fresh)

    if base.empty and old_updates.empty:
        if not fetched_parts:
            raise RuntimeError("Ingen FX-data kunde bootstrapas.")
        initial = _normalise_fx(pd.concat(fetched_parts, ignore_index=True))
        _write_fx(initial, base_file)
        print(f"FX-bas skapad: {len(initial)} rader i {_resolve(base_file)}")
        return initial

    updates = old_updates.copy()
    for fresh in fetched_parts:
        pair_base = str(fresh.iloc[0]["base_currency"])
        pair_quote = str(fresh.iloc[0]["quote_currency"])
        first_fresh_date = fresh["date"].min()
        if not updates.empty:
            keep = ~(
                (updates["base_currency"] == pair_base)
                & (updates["quote_currency"] == pair_quote)
                & (updates["date"] >= first_fresh_date)
            )
            updates = updates.loc[keep].copy()
        updates = pd.concat([updates, fresh], ignore_index=True)

    updates = _normalise_fx(updates)
    _write_fx(updates, updates_file)
    combined = load_fx_history(base_file, updates_file)
    print(f"FX-historik klar: {len(combined)} rader för {len(pairs)} valutapar.")
    return combined


def convert_values_to_currency(
    frame: pd.DataFrame,
    *,
    value_column: str,
    date_column: str,
    base_currency: str,
    quote_currency: str,
    fx_history: pd.DataFrame,
    output_column: str,
    rate_column: str = "FX_RATE",
) -> pd.DataFrame:
    result = frame.copy()
    base = str(base_currency).strip().upper()
    quote = str(quote_currency).strip().upper()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce").dt.tz_localize(None).dt.normalize()
    result[value_column] = pd.to_numeric(result[value_column], errors="coerce")

    if base == quote:
        result[rate_column] = 1.0
        result[output_column] = result[value_column]
        return result

    fx = _normalise_fx(fx_history)
    pair = fx.loc[
        (fx["base_currency"] == base)
        & (fx["quote_currency"] == quote),
        ["date", "rate"],
    ].copy()
    if pair.empty:
        result[rate_column] = pd.NA
        result[output_column] = pd.NA
        return result

    pair = pair.sort_values("date").rename(columns={"date": "fx_date", "rate": rate_column})
    left = result.sort_values(date_column).reset_index(drop=True)
    merged = pd.merge_asof(
        left,
        pair,
        left_on=date_column,
        right_on="fx_date",
        direction="backward",
        allow_exact_matches=False,
    )
    merged[output_column] = pd.to_numeric(merged[value_column], errors="coerce") * pd.to_numeric(
        merged[rate_column], errors="coerce"
    )
    return merged.drop(columns=["fx_date"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hämta och lagra dagskurser för valutapar som behövs för EPS-värderingen."
    )
    parser.add_argument("--base-file", type=Path, default=FX_BASE_FILE)
    parser.add_argument("--updates-file", type=Path, default=FX_UPDATES_FILE)
    parser.add_argument("--full-start", default=DEFAULT_FX_START)
    args = parser.parse_args()
    update_fx(args.base_file, args.updates_file, full_start=args.full_start)


if __name__ == "__main__":
    main()
