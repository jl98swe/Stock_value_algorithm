from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import REPORTS_FILE, load_reports, save_reports

ALIGNED_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_aligned.csv"
ALIGNMENT_AUDIT_FILE = ROOT / "data" / "derived" / "eps_alignment_audit.csv"
COMPATIBILITY_FILE = ROOT / "data" / "derived" / "eps_reference_compatibility_audit.csv"
STRICT_THRESHOLD_PCT = 1.0
MIN_OVERLAPS = 4
STRICT_IMPORT_MARKER = "strict_reference_gap_fill_v1"
YAHOO_STATUSES = {
    "yahoo_trailing_diluted",
    "yahoo_reconstructed_diluted_ttm",
}
FALLBACK_STATUS = "fallback_user_history"
STRICT_FILL_STATUS = "strict_user_history_gap_fill"
STRICT_FILL_SOURCE = "User-supplied historical EPS TTM / all Yahoo overlaps <1%"


def _compatibility(audit: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, group in audit.groupby("ticker", sort=True):
        overlap = group.loc[group["alignment_status"].astype(str).isin(YAHOO_STATUSES)].copy()
        overlap["abs_change_pct"] = pd.to_numeric(overlap["abs_change_pct"], errors="coerce")
        overlap = overlap.dropna(subset=["abs_change_pct"])
        max_diff = float(overlap["abs_change_pct"].max()) if not overlap.empty else float("nan")
        violating = overlap.loc[overlap["abs_change_pct"] >= STRICT_THRESHOLD_PCT]
        strict = len(overlap) >= MIN_OVERLAPS and violating.empty
        rows.append(
            {
                "ticker": str(ticker),
                "overlap_periods": len(overlap),
                "max_abs_diff_pct": max_diff,
                "periods_at_or_above_1pct": len(violating),
                "strict_compatible": strict,
                "policy": "every comparable Yahoo period must be <1%; median is ignored",
            }
        )
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def _remove_previous_strict_imports(reports_file: Path = REPORTS_FILE) -> int:
    reports = load_reports(reports_file)
    if reports.empty:
        return 0
    mask = reports["notes"].fillna("").astype(str).str.contains(STRICT_IMPORT_MARKER, regex=False)
    removed = int(mask.sum())
    if removed:
        save_reports(reports.loc[~mask].copy(), reports_file)
    return removed


def apply(
    aligned_file: Path = ALIGNED_FILE,
    audit_file: Path = ALIGNMENT_AUDIT_FILE,
    compatibility_file: Path = COMPATIBILITY_FILE,
) -> pd.DataFrame:
    aligned = pd.read_csv(aligned_file, encoding="utf-8-sig")
    audit = pd.read_csv(audit_file, encoding="utf-8-sig")
    compatibility = _compatibility(audit)

    allowed = set(
        compatibility.loc[compatibility["strict_compatible"].astype(bool), "ticker"].astype(str)
    )
    mask = (
        aligned["ticker"].astype(str).isin(allowed)
        & aligned["alignment_status"].astype(str).eq(FALLBACK_STATUS)
    )
    aligned.loc[mask, "alignment_status"] = STRICT_FILL_STATUS
    aligned.loc[mask, "eps_source"] = STRICT_FILL_SOURCE

    aligned.to_csv(aligned_file, index=False)
    compatibility_file.parent.mkdir(parents=True, exist_ok=True)
    compatibility.to_csv(compatibility_file, index=False)
    removed = _remove_previous_strict_imports()

    print(
        f"Strikt Börsdata-referenspolicy: {int(compatibility['strict_compatible'].sum())}/{len(compatibility)} "
        f"tickers klarar kravet att VARJE Yahoo-överlapp är <{STRICT_THRESHOLD_PCT:.0f}%. "
        f"{int(mask.sum())} tidigare luckrader får användas som historisk gap-fill. "
        f"{removed} gamla strict-gap-fill-rader rensades före återimport."
    )
    failed = compatibility.loc[~compatibility["strict_compatible"].astype(bool)]
    if not failed.empty:
        print("Tickers som inte klarar strikt <1%-regel eller har för få överlapp:")
        print(
            failed[["ticker", "overlap_periods", "max_abs_diff_pct", "periods_at_or_above_1pct"]]
            .to_string(index=False)
        )
    return compatibility


if __name__ == "__main__":
    apply()
