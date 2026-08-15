from __future__ import annotations

import argparse
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
    "ttm_diluted_eps",
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
    company = yf.Ticker(ticker)

    try:
        quarterly = company.quarterly_income_stmt
    except Exception as exc:
        print(f"VARNING {ticker}: quarterly_income_stmt misslyckades: {exc}")
        quarterly = pd.DataFrame()

    diluted = _row(quarterly, ("Diluted EPS", "DilutedEPS"))
    period_end: str | None = None
    latest_quarter_eps: float | None = None
    derived_ttm: float | None = None

    if diluted is not None and not diluted.empty:
        series = pd.to_numeric(diluted, errors="coerce").dropna()
        parsed: list[tuple[pd.Timestamp, float]] = []
        for column, value in series.items():
            parsed_date = pd.to_datetime(column, errors="coerce")
            if pd.notna(parsed_date):
                timestamp = pd.Timestamp(parsed_date)
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.tz_convert(None)
                parsed.append((timestamp, float(value)))
        parsed.sort(key=lambda item: item[0], reverse=True)
        if parsed:
            period_end = parsed[0][0].date().isoformat()
            latest_quarter_eps = parsed[0][1]
            if len(parsed) >= 4:
                derived_ttm = float(sum(value for _, value in parsed[:4]))

    ttm_eps: float | None = None
    try:
        ttm = company.ttm_income_stmt
        ttm_row = _row(ttm, ("Diluted EPS", "DilutedEPS"))
        if ttm_row is not None:
            values = pd.to_numeric(ttm_row, errors="coerce").dropna()
            if not values.empty:
                ttm_eps = float(values.iloc[0])
    except Exception as exc:
        print(f"INFO {ticker}: ingen användbar ttm_income_stmt: {exc}")

    if latest_quarter_eps is None and derived_ttm is None and ttm_eps is None:
        return None

    note_parts = [
        "AUTOMATISK KANDIDAT - används aldrig av värderingsalgoritmen förrän manuellt verifierad.",
        "Yahoo saknar tillförlitlig publiceringstid/effective_date i detta flöde.",
    ]
    if derived_ttm is not None and ttm_eps is not None:
        note_parts.append(f"Kontroll: summa 4 kvartal={derived_ttm:.6g}, Yahoo TTM={ttm_eps:.6g}.")

    return {
        "ticker": ticker,
        "period_end": period_end,
        "quarterly_diluted_eps": latest_quarter_eps,
        "derived_eps_ttm": derived_ttm,
        "ttm_diluted_eps": ttm_eps,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance / yfinance",
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
) -> pd.DataFrame:
    if tickers is None:
        prices = load_price_history(BASE_DATA_FILE, UPDATES_FILE)
        tickers = sorted(prices["ticker"].dropna().astype(str).unique().tolist())

    rows: list[dict[str, object]] = []
    for index, ticker in enumerate(tickers, start=1):
        print(f"Fundamenta {index}/{len(tickers)}: {ticker}")
        try:
            candidate = _quarterly_candidate(ticker)
        except Exception as exc:
            print(f"VARNING {ticker}: kunde inte hämta fundamental kandidat: {exc}")
            candidate = None
        if candidate is not None:
            rows.append(candidate)

    frame = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
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
    args = parser.parse_args()
    update_fundamental_candidates(args.output, tickers=args.tickers)


if __name__ == "__main__":
    main()
