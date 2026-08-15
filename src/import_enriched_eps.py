from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import REPORTS_FILE, load_reports, save_reports
from .fx import STOCK_METADATA_FILE, load_stock_currencies

SOURCE_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
IMPORT_MARKER = "historical_eps_same_day_policy_v1"
IMPORT_SOURCE = "User-supplied historical EPS TTM; report date from Yahoo/official override"


def _load_source(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(path)

    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Historisk EPS saknar kolumner: {', '.join(missing)}")

    frame = frame[required].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["report_period"] = frame["report_period"].astype(str).str.strip()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame["eps_ttm"] = pd.to_numeric(frame["eps_ttm"], errors="coerce")
    frame["currency"] = frame["currency"].astype(str).str.strip().str.upper()

    if frame[["ticker", "report_period", "report_date", "eps_ttm", "currency"]].isna().any().any():
        bad = frame.loc[
            frame[["ticker", "report_period", "report_date", "eps_ttm", "currency"]].isna().any(axis=1),
            ["ticker", "report_period"],
        ]
        raise ValueError(f"Historisk EPS innehåller ofullständiga rader: {bad.head(10).to_dict('records')}")
    if frame.duplicated(["ticker", "report_period"]).any():
        raise ValueError("Historisk EPS innehåller dubbla ticker + report_period")

    return frame.sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)


def _validate_currencies(source: pd.DataFrame, metadata: pd.DataFrame) -> None:
    if metadata.empty:
        raise ValueError(f"Bolagsmetadata saknas: {STOCK_METADATA_FILE}")

    check = source.merge(
        metadata[["ticker", "report_currency", "price_currency"]],
        on="ticker",
        how="left",
        validate="many_to_one",
    )
    if check["report_currency"].isna().any():
        missing = sorted(check.loc[check["report_currency"].isna(), "ticker"].unique())
        raise ValueError(f"Saknar valutametadata för: {', '.join(missing[:20])}")

    mismatch = check.loc[check["currency"] != check["report_currency"]]
    if not mismatch.empty:
        sample = mismatch[["ticker", "currency", "report_currency"]].drop_duplicates().head(20)
        raise ValueError(f"EPS-valuta matchar inte report_currency: {sample.to_dict('records')}")


def _generated_reports(source: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in source.itertuples(index=False):
        report_date = pd.Timestamp(row.report_date).date().isoformat()
        rows.append(
            {
                "ticker": row.ticker,
                "period_end": "",
                "report_period": row.report_period,
                # Exakt publiceringstid lagras inte historiskt. Projektregeln är
                # medvetet att EPS alltid gäller samma börsdag som report_date.
                "published_at": "",
                "effective_date": report_date,
                "eps_ttm": float(row.eps_ttm),
                "source": IMPORT_SOURCE,
                "verified": True,
                "verified_at": "",
                "notes": (
                    f"{IMPORT_MARKER}; effective_date=report_date; "
                    f"report_currency={row.currency}; exact publication time not tracked"
                ),
            }
        )
    return pd.DataFrame(rows)


def import_history(
    source_file: Path = SOURCE_FILE,
    reports_file: Path = REPORTS_FILE,
) -> pd.DataFrame:
    source = _load_source(source_file)
    metadata = load_stock_currencies()
    _validate_currencies(source, metadata)

    generated = _generated_reports(source)
    existing = load_reports(reports_file)

    # Rader som lagts in manuellt eller via andra verifieringsflöden har
    # företräde. Endast tidigare rader från just denna historikimport ersätts.
    existing_notes = existing["notes"].astype(str) if not existing.empty else pd.Series(dtype=str)
    manual = existing.loc[~existing_notes.str.contains(IMPORT_MARKER, regex=False, na=False)].copy()
    manual_keys = set(zip(manual["ticker"].astype(str), manual["report_period"].astype(str)))
    if manual_keys:
        generated = generated.loc[
            ~generated.apply(lambda row: (str(row["ticker"]), str(row["report_period"])) in manual_keys, axis=1)
        ].copy()

    combined = pd.concat([manual, generated], ignore_index=True)
    save_reports(combined, reports_file)
    saved = load_reports(reports_file)

    imported_count = int(saved["notes"].astype(str).str.contains(IMPORT_MARKER, regex=False, na=False).sum())
    expected = len(source) - len(
        {(ticker, period) for ticker, period in manual_keys if ((source["ticker"] == ticker) & (source["report_period"] == period)).any()}
    )
    if imported_count != expected:
        raise ValueError(f"Importerade {imported_count} historiska rapporter, förväntade {expected}")

    same_day = saved.loc[saved["notes"].astype(str).str.contains(IMPORT_MARKER, regex=False, na=False)]
    if not (same_day["effective_date"].dt.normalize() == pd.to_datetime(source.set_index(["ticker", "report_period"])["report_date"])
            .reindex(pd.MultiIndex.from_frame(same_day[["ticker", "report_period"]]))
            .reset_index(drop=True)
            .dt.normalize()).all():
        raise ValueError("Same-day-regeln för effective_date kunde inte verifieras")

    print(
        f"Historisk EPS importerad: {imported_count} rader för "
        f"{same_day['ticker'].nunique()} tickers. effective_date = report_date för samtliga importerade rader."
    )
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importera berikad historisk EPS till reports.csv med same-day effective_date."
    )
    parser.add_argument("--source", type=Path, default=SOURCE_FILE)
    parser.add_argument("--reports", type=Path, default=REPORTS_FILE)
    args = parser.parse_args()
    import_history(args.source, args.reports)


if __name__ == "__main__":
    main()
