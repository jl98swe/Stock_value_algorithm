from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import REPORTS_FILE, load_reports, save_reports
from .fx import STOCK_METADATA_FILE, load_stock_currencies

SOURCE_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_aligned.csv"
IMPORT_MARKER = "historical_eps_yahoo_diluted_v2"
LEGACY_IMPORT_MARKER = "historical_eps_same_day_policy_v1"
DEFAULT_IMPORT_SOURCE = "Yahoo Finance / trailingDilutedEPS historical timeseries"
COMPARABLE_STATUSES = {
    "yahoo_trailing_diluted",
    "yahoo_reconstructed_diluted_ttm",
}


def _load_source(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(path)

    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Historisk EPS saknar kolumner: {', '.join(missing)}")

    for column, default in (
        ("period_end", ""),
        ("eps_source", DEFAULT_IMPORT_SOURCE),
        ("alignment_status", "legacy_input"),
    ):
        if column not in frame.columns:
            frame[column] = default

    columns = required + ["period_end", "eps_source", "alignment_status"]
    frame = frame[columns].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["report_period"] = frame["report_period"].astype(str).str.strip()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame["period_end"] = pd.to_datetime(frame["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame["eps_ttm"] = pd.to_numeric(frame["eps_ttm"], errors="coerce")
    frame["currency"] = frame["currency"].astype(str).str.strip().str.upper()
    frame["eps_source"] = frame["eps_source"].fillna(DEFAULT_IMPORT_SOURCE).astype(str).str.strip()
    frame["alignment_status"] = frame["alignment_status"].fillna("unknown").astype(str).str.strip()

    required_for_row = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    if frame[required_for_row].isna().any().any():
        bad = frame.loc[
            frame[required_for_row].isna().any(axis=1),
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
    # Endast rader som verkligen har samma diluted EPS-definition som framtida
    # Yahoo-data får bli kanoniska. Den uppladdade fallbackhistoriken ligger kvar
    # i aligned/audit-filerna som referens men påverkar inte P/E eller score.
    comparable = source.loc[source["alignment_status"].astype(str).isin(COMPARABLE_STATUSES)].copy()
    rows: list[dict[str, object]] = []
    for row in comparable.itertuples(index=False):
        report_date = pd.Timestamp(row.report_date).date().isoformat()
        period_end = pd.Timestamp(row.period_end).date().isoformat() if pd.notna(row.period_end) else ""
        eps_source = str(row.eps_source or DEFAULT_IMPORT_SOURCE).strip()
        rows.append(
            {
                "ticker": row.ticker,
                "period_end": period_end,
                "report_period": row.report_period,
                "published_at": "",
                "effective_date": report_date,
                "eps_ttm": float(row.eps_ttm),
                "source": eps_source,
                "verified": True,
                "verified_at": "",
                "notes": (
                    f"{IMPORT_MARKER}; effective_date=report_date; "
                    f"report_currency={row.currency}; alignment_status={row.alignment_status}; "
                    "metric=trailingDilutedEPS; exact publication time not tracked"
                ),
            }
        )
    return pd.DataFrame(rows)


def _historical_generated_mask(notes: pd.Series) -> pd.Series:
    text = notes.astype(str)
    return (
        text.str.contains(IMPORT_MARKER, regex=False, na=False)
        | text.str.contains(LEGACY_IMPORT_MARKER, regex=False, na=False)
    )


def import_history(
    source_file: Path = SOURCE_FILE,
    reports_file: Path = REPORTS_FILE,
) -> pd.DataFrame:
    source = _load_source(source_file)
    metadata = load_stock_currencies()
    _validate_currencies(source, metadata)

    generated = _generated_reports(source)
    existing = load_reports(reports_file)

    # Riktigt manuella/andra verifierade poster har alltid företräde. Däremot
    # ersätter v2-importen den gamla användar-/Börsdata-baserade historikimporten
    # så att endast samma Yahoo diluted-definition används bakåt och framåt.
    generated_mask = _historical_generated_mask(existing["notes"]) if not existing.empty else pd.Series(dtype=bool)
    manual = existing.loc[~generated_mask].copy() if not existing.empty else existing.copy()
    manual_keys = set(zip(manual["ticker"].astype(str), manual["report_period"].astype(str)))
    if manual_keys and not generated.empty:
        generated = generated.loc[
            ~generated.apply(lambda row: (str(row["ticker"]), str(row["report_period"])) in manual_keys, axis=1)
        ].copy()

    expected = len(generated)
    combined = pd.concat([manual, generated], ignore_index=True)
    save_reports(combined, reports_file)
    saved = load_reports(reports_file)

    imported = saved.loc[
        saved["notes"].astype(str).str.contains(IMPORT_MARKER, regex=False, na=False)
    ].copy()
    if len(imported) != expected:
        raise ValueError(f"Importerade {len(imported)} jämförbara historiska rapporter, förväntade {expected}")

    source_dates = source.set_index(["ticker", "report_period"])["report_date"]
    imported_keys = pd.MultiIndex.from_frame(imported[["ticker", "report_period"]])
    expected_dates = source_dates.reindex(imported_keys).reset_index(drop=True).dt.normalize()
    actual_dates = imported["effective_date"].reset_index(drop=True).dt.normalize()
    if not actual_dates.equals(expected_dates):
        raise ValueError("Same-day-regeln för effective_date kunde inte verifieras")

    statuses = source["alignment_status"].astype(str)
    yahoo_direct = int(statuses.eq("yahoo_trailing_diluted").sum())
    yahoo_reconstructed = int(statuses.eq("yahoo_reconstructed_diluted_ttm").sum())
    fallback = int(statuses.eq("fallback_user_history").sum())
    print(
        f"Historisk EPS importerad: {len(imported)} jämförbara rader för {imported['ticker'].nunique()} tickers. "
        f"Underlaget har {yahoo_direct} direkta Yahoo trailingDilutedEPS, "
        f"{yahoo_reconstructed} Yahoo-rekonstruerade diluted TTM och {fallback} referens-fallbacks som INTE importeras. "
        "effective_date = report_date för samtliga importerade rader."
    )
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Importera endast Yahoo-jämförbar historisk diluted EPS till reports.csv; fallbackhistorik hålls utanför värderingen."
        )
    )
    parser.add_argument("--source", type=Path, default=SOURCE_FILE)
    parser.add_argument("--reports", type=Path, default=REPORTS_FILE)
    args = parser.parse_args()
    import_history(args.source, args.reports)


if __name__ == "__main__":
    main()
