from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import REPORT_COLUMNS, load_reports, save_reports
from .fx import load_stock_currencies

SOURCE_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_aligned.csv"
REPORTS_FILE = ROOT / "data" / "fundamentals" / "reports.csv"
STATUS = "strict_user_history_gap_fill"
IMPORT_MARKER = "strict_reference_gap_fill_v1"


def import_gap_fill(
    source_file: Path = SOURCE_FILE,
    reports_file: Path = REPORTS_FILE,
) -> pd.DataFrame:
    source = pd.read_csv(source_file, encoding="utf-8-sig")
    required = ["ticker", "report_period", "report_date", "eps_ttm", "currency", "alignment_status", "eps_source"]
    missing = [column for column in required if column not in source.columns]
    if missing:
        raise ValueError(f"Strict gap-fill saknar kolumner: {', '.join(missing)}")

    source = source.loc[source["alignment_status"].astype(str).eq(STATUS)].copy()
    source["report_date"] = pd.to_datetime(source["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    source["eps_ttm"] = pd.to_numeric(source["eps_ttm"], errors="coerce")
    source["currency"] = source["currency"].fillna("").astype(str).str.strip().str.upper()
    source = source.dropna(subset=["ticker", "report_period", "report_date", "eps_ttm"])

    metadata = load_stock_currencies()
    check = source.merge(metadata[["ticker", "report_currency"]], on="ticker", how="left", validate="many_to_one")
    check["report_currency"] = check["report_currency"].fillna("").astype(str).str.upper()
    mismatch = check.loc[check["currency"] != check["report_currency"]]
    if not mismatch.empty:
        raise ValueError(
            "Strict gap-fill har valutakonflikt: "
            + str(mismatch[["ticker", "report_period", "currency", "report_currency"]].to_dict("records"))
        )

    existing = load_reports(reports_file)
    if existing.empty:
        preserved = existing.copy()
    else:
        strict_old = existing["notes"].fillna("").astype(str).str.contains(IMPORT_MARKER, regex=False)
        preserved = existing.loc[~strict_old].copy()

    existing_keys = set(zip(preserved["ticker"].astype(str), preserved["report_period"].astype(str)))
    rows: list[dict[str, object]] = []
    skipped_existing = 0
    for row in source.itertuples(index=False):
        key = (str(row.ticker), str(row.report_period))
        if key in existing_keys:
            skipped_existing += 1
            continue
        report_date = pd.Timestamp(row.report_date).date().isoformat()
        rows.append(
            {
                "ticker": str(row.ticker),
                "period_end": "",
                "report_period": str(row.report_period),
                "published_at": "",
                "effective_date": report_date,
                "eps_ttm": float(row.eps_ttm),
                "source": str(row.eps_source),
                "verified": True,
                "verified_at": "",
                "notes": (
                    f"{IMPORT_MARKER}; effective_date=report_date; report_currency={row.currency}; "
                    "historical reference accepted only because every available Yahoo diluted EPS overlap for the ticker is <1%; "
                    "median is not used; exact publication time not tracked"
                ),
            }
        )

    generated = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    combined = pd.concat([preserved, generated], ignore_index=True)
    save_reports(combined, reports_file)
    saved = load_reports(reports_file)
    print(
        f"Strikt historisk gap-fill importerad: {len(generated)} rader från {generated['ticker'].nunique() if not generated.empty else 0} tickers; "
        f"{skipped_existing} rader hoppades över eftersom en bättre kanonisk rad redan fanns."
    )
    return saved


if __name__ == "__main__":
    import_gap_fill()
