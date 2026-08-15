from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import ROOT
from .fetch_data import BASE_DATA_FILE, UPDATES_FILE, load_price_history
from .utils import write_json_atomic

CANDIDATES_FILE = ROOT / "data" / "fundamentals" / "yahoo_eps_candidates.csv"
CANDIDATES_JSON = ROOT / "docs" / "data" / "fundamental_candidates.json"
CANDIDATE_COLUMNS = [
    "ticker",
    "period_end",
    "quarterly_diluted_eps",
    "derived_eps_ttm",
    "quarter_count",
    "fetched_at",
    "source",
    "verified",
    "notes",
]


def _row(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    lookup = {str(index).strip().lower(): index for index in frame.index}
    for name in names:
        key = name.lower()
        if key in lookup:
            values = frame.loc[lookup[key]]
            return values if isinstance(values, pd.Series) else pd.Series(values)
    return None


def _quarterly_candidate(ticker: str) -> dict[str, object] | None:
    """Hämta endast resultaträkningens Diluted EPS från Yahoo.

    ``earnings_dates -> Reported EPS`` används avsiktligt inte eftersom det kan
    vara en annan EPS-definition än den som finns i själva resultaträkningen.
    Yahoo-raden är dessutom bara en granskningskandidat; den kan aldrig aktivera
    värderingsscoren innan publiceringstid och effective_date har verifierats.
    """
    try:
        quarterly = yf.Ticker(ticker).quarterly_income_stmt
    except Exception as exc:
        print(f"VARNING {ticker}: quarterly_income_stmt misslyckades: {exc}")
        return None

    diluted = _row(quarterly, ("Diluted EPS", "DilutedEPS"))
    if diluted is None or diluted.empty:
        return None

    series = pd.to_numeric(diluted, errors="coerce").dropna()
    parsed: list[tuple[pd.Timestamp, float]] = []
    for column, value in series.items():
        parsed_date = pd.to_datetime(column, errors="coerce")
        if pd.isna(parsed_date):
            continue
        timestamp = pd.Timestamp(parsed_date)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert(None)
        parsed.append((timestamp, float(value)))

    parsed.sort(key=lambda item: item[0], reverse=True)
    if not parsed:
        return None

    quarter_count = min(len(parsed), 4)
    latest_period, latest_eps = parsed[0]
    derived_ttm = float(sum(value for _, value in parsed[:4])) if len(parsed) >= 4 else None
    components = ", ".join(
        f"{period.date().isoformat()}={value:.6g}" for period, value in parsed[:4]
    )

    note_parts = [
        "AUTOMATISK KANDIDAT - används aldrig av värderingsalgoritmen förrän manuellt verifierad.",
        "Källa är Diluted EPS i Yahoo-resultaträkningen, inte Reported EPS från earnings_dates.",
        "Yahoo saknar tillförlitlig publiceringstid/effective_date i detta flöde.",
        f"Senaste kvartal som ingår: {components}.",
    ]
    if derived_ttm is None:
        note_parts.append("Färre än fyra användbara kvartal hittades; EPS TTM har därför inte härletts.")

    return {
        "ticker": ticker,
        "period_end": latest_period.date().isoformat(),
        "quarterly_diluted_eps": latest_eps,
        "derived_eps_ttm": derived_ttm,
        "quarter_count": quarter_count,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance / quarterly_income_stmt / Diluted EPS",
        "verified": False,
        "notes": " ".join(note_parts),
    }


def _json_value(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (float, int)):
        return float(value)
    return value


def _publish_review_json(frame: pd.DataFrame) -> None:
    records: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        records.append({key: _json_value(value) for key, value in row.items()})
    write_json_atomic(
        CANDIDATES_JSON,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Yahoo-värden är endast granskningskandidater och används inte i score förrän de finns verifierade i reports.csv.",
            "candidates": records,
        },
    )


def update_fundamental_candidates(
    output_file: Path = CANDIDATES_FILE,
    *,
    tickers: list[str] | None = None,
    workers: int = 4,
) -> pd.DataFrame:
    if tickers is None:
        prices = load_price_history(BASE_DATA_FILE, UPDATES_FILE)
        tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(_quarterly_candidate, ticker): ticker for ticker in tickers}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            ticker = futures[future]
            try:
                candidate = future.result()
            except Exception as exc:
                print(f"VARNING {ticker}: kunde inte hämta fundamental kandidat: {exc}")
                candidate = None
            if candidate is not None:
                rows.append(candidate)
            print(f"Fundamenta {completed}/{len(tickers)} klar: {ticker}")

    frame = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values("ticker").reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_file, index=False)
    _publish_review_json(frame)
    print(f"Sparade {len(frame)} Yahoo EPS-kandidater till {output_file}")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hämta Yahoo EPS-kandidater för manuell verifiering. Kandidater aktiverar aldrig score automatiskt."
    )
    parser.add_argument("--output", type=Path, default=CANDIDATES_FILE)
    parser.add_argument("--ticker", action="append", dest="tickers", help="Begränsa till en eller flera tickers.")
    parser.add_argument("--workers", type=int, default=4, help="Parallella Yahoo-anrop (standard 4).")
    args = parser.parse_args()
    update_fundamental_candidates(args.output, tickers=args.tickers, workers=args.workers)


if __name__ == "__main__":
    main()
