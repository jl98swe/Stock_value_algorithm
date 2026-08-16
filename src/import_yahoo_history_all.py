from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import REPORT_COLUMNS, load_reports, save_reports
from .fx import load_stock_currencies

SOURCE_FILE = ROOT / "data" / "fundamentals" / "yahoo_history_all.csv"
IMPORT_MARKER = "yahoo_history_all_v1"
COMPARABLE_STATUSES = {
    "yahoo_trailing_diluted",
    "yahoo_reconstructed_diluted_ttm",
}


def _load_source(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = [
        "ticker",
        "period_end",
        "report_date",
        "eps_ttm",
        "currency",
        "alignment_status",
        "eps_source",
        "date_status",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Yahoo-historiken saknar kolumner: {', '.join(missing)}")

    result = frame[required].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["period_end"] = pd.to_datetime(result["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["report_date"] = pd.to_datetime(result["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["currency"] = result["currency"].fillna("").astype(str).str.strip().str.upper()
    result["alignment_status"] = result["alignment_status"].astype(str).str.strip()
    result["eps_source"] = result["eps_source"].astype(str).str.strip()
    result["date_status"] = result["date_status"].astype(str).str.strip()
    result = result.dropna(subset=["ticker", "period_end", "eps_ttm"])
    result = result.loc[result["ticker"].str.len() > 0]
    if result.duplicated(["ticker", "period_end"]).any():
        raise ValueError("Yahoo-historiken innehåller dubbla ticker + period_end")
    return result.sort_values(["ticker", "period_end"]).reset_index(drop=True)


def _generated_mask(reports: pd.DataFrame) -> pd.Series:
    if reports.empty:
        return pd.Series(dtype=bool)
    return reports["notes"].fillna("").astype(str).str.contains(IMPORT_MARKER, regex=False)


def import_history(
    source_file: Path = SOURCE_FILE,
) -> pd.DataFrame:
    source = _load_source(source_file)
    source = source.loc[
        source["alignment_status"].isin(COMPARABLE_STATUSES)
        & source["report_date"].notna()
        & source["currency"].str.len().gt(0)
    ].copy()

    metadata = load_stock_currencies()
    if metadata.empty:
        raise ValueError("stocks_yahoo.csv saknar valutametadata")
    source = source.merge(
        metadata[["ticker", "report_currency"]],
        on="ticker",
        how="left",
        validate="many_to_one",
    )
    source["report_currency"] = source["report_currency"].fillna("").astype(str).str.upper()
    currency_mismatch = source.loc[source["currency"] != source["report_currency"]]
    if not currency_mismatch.empty:
        sample = currency_mismatch[["ticker", "period_end", "currency", "report_currency"]].head(20)
        raise ValueError(f"Yahoo historisk EPS-valuta avviker från metadata: {sample.to_dict('records')}")

    existing = load_reports()
    generated_mask = _generated_mask(existing)
    preserved = existing.loc[~generated_mask].copy() if not existing.empty else existing.copy()

    existing_period_keys = {
        (str(row.ticker), pd.Timestamp(row.period_end).normalize())
        for row in preserved.dropna(subset=["period_end"]).itertuples(index=False)
    }

    rows: list[dict[str, object]] = []
    skipped_existing = 0
    for row in source.itertuples(index=False):
        period_end = pd.Timestamp(row.period_end).normalize()
        key = (str(row.ticker), period_end)
        if key in existing_period_keys:
            skipped_existing += 1
            continue
        report_date = pd.Timestamp(row.report_date).normalize()
        rows.append(
            {
                "ticker": str(row.ticker),
                "period_end": period_end,
                "report_period": f"YAHOO-{period_end.date().isoformat()}",
                "published_at": pd.NaT,
                "effective_date": report_date,
                "eps_ttm": float(row.eps_ttm),
                "source": str(row.eps_source),
                "verified": True,
                "verified_at": datetime.now(timezone.utc),
                "notes": (
                    f"{IMPORT_MARKER}; metric=trailingDilutedEPS; report_currency={row.currency}; "
                    f"alignment_status={row.alignment_status}; date_status={row.date_status}; "
                    "effective_date=report_date"
                ),
            }
        )

    generated = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    combined = pd.concat([preserved, generated], ignore_index=True)
    save_reports(combined)
    saved = load_reports()

    imported = saved.loc[
        saved["notes"].fillna("").astype(str).str.contains(IMPORT_MARKER, regex=False)
    ]
    print(
        f"Yahoo-historik för hela universum importerad: {len(imported)} nya kanoniska perioder; "
        f"{skipped_existing} perioder fanns redan i kanonisk historik; "
        f"{source['ticker'].nunique()} tickers hade minst en importbar Yahoo-period."
    )
    return saved


if __name__ == "__main__":
    import_history()
