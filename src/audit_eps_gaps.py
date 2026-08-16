from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT

ALIGNMENT_FILE = ROOT / "data" / "derived" / "eps_alignment_audit.csv"
YAHOO_HISTORY_FILE = ROOT / "data" / "fundamentals" / "yahoo_history_all.csv"
REFERENCE_GAPS_FILE = ROOT / "data" / "derived" / "eps_reference_gap_audit.csv"
CONTINUITY_FILE = ROOT / "data" / "derived" / "yahoo_history_continuity_audit.csv"
COMPARABLE = {"yahoo_trailing_diluted", "yahoo_reconstructed_diluted_ttm"}


def _audit_reference_gaps(alignment_file: Path) -> pd.DataFrame:
    frame = pd.read_csv(alignment_file, encoding="utf-8-sig")
    if frame.empty:
        return pd.DataFrame()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame = frame.sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for ticker, group in frame.groupby("ticker", sort=True):
        group = group.reset_index(drop=True)
        comparable_indices = [
            index for index, status in enumerate(group["alignment_status"].astype(str)) if status in COMPARABLE
        ]
        for index, row in group.iterrows():
            if str(row["alignment_status"]) != "fallback_user_history":
                continue
            previous = [value for value in comparable_indices if value < index]
            following = [value for value in comparable_indices if value > index]
            prev_row = group.iloc[max(previous)] if previous else None
            next_row = group.iloc[min(following)] if following else None

            if prev_row is not None and next_row is not None:
                position = "internal"
                action = "borsdata_reference_plus_report_verification"
            elif prev_row is None and next_row is not None:
                position = "leading"
                action = "optional_backfill_only"
            elif prev_row is not None and next_row is None:
                position = "trailing"
                action = "verify_latest_period"
            else:
                position = "isolated"
                action = "manual_verification_required"

            report_date = pd.Timestamp(row["report_date"]) if pd.notna(row["report_date"]) else pd.NaT
            prev_date = pd.Timestamp(prev_row["report_date"]) if prev_row is not None else pd.NaT
            next_date = pd.Timestamp(next_row["report_date"]) if next_row is not None else pd.NaT
            rows.append(
                {
                    "ticker": ticker,
                    "report_period": row["report_period"],
                    "report_date": report_date.date().isoformat() if pd.notna(report_date) else "",
                    "gap_position": position,
                    "previous_comparable_period": prev_row["report_period"] if prev_row is not None else "",
                    "previous_comparable_date": prev_date.date().isoformat() if pd.notna(prev_date) else "",
                    "next_comparable_period": next_row["report_period"] if next_row is not None else "",
                    "next_comparable_date": next_date.date().isoformat() if pd.notna(next_date) else "",
                    "days_from_previous": int((report_date - prev_date).days) if pd.notna(report_date) and pd.notna(prev_date) else pd.NA,
                    "days_to_next": int((next_date - report_date).days) if pd.notna(report_date) and pd.notna(next_date) else pd.NA,
                    "stale_window_days": int((next_date - report_date).days) if position == "internal" and pd.notna(next_date) and pd.notna(report_date) else pd.NA,
                    "reference_eps_ttm": row.get("original_eps_ttm", row.get("aligned_eps_ttm", pd.NA)),
                    "currency": row.get("currency", ""),
                    "recommended_action": action,
                }
            )
    return pd.DataFrame(rows)


def _audit_yahoo_continuity(history_file: Path) -> pd.DataFrame:
    frame = pd.read_csv(history_file, encoding="utf-8-sig")
    if frame.empty:
        return pd.DataFrame()
    frame["period_end"] = pd.to_datetime(frame["period_end"], errors="coerce")
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "period_end"]).sort_values(["ticker", "period_end"])

    rows: list[dict[str, object]] = []
    for ticker, group in frame.groupby("ticker", sort=True):
        group = group.drop_duplicates("period_end", keep="last").sort_values("period_end").reset_index(drop=True)
        if group.empty:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]
        if pd.isna(first["report_date"]):
            rows.append(
                {
                    "ticker": ticker,
                    "gap_type": "leading_missing_report_date",
                    "previous_period_end": "",
                    "next_period_end": pd.Timestamp(first["period_end"]).date().isoformat(),
                    "gap_days": pd.NA,
                    "estimated_missing_quarters": pd.NA,
                    "detail": "Första Yahoo-perioden saknar säkert rapportdatum.",
                }
            )

        for left_index in range(len(group) - 1):
            left = group.iloc[left_index]
            right = group.iloc[left_index + 1]
            left_end = pd.Timestamp(left["period_end"])
            right_end = pd.Timestamp(right["period_end"])
            gap_days = int((right_end - left_end).days)
            if gap_days > 140:
                estimated = max(1, int(round(gap_days / 91.25)) - 1)
                rows.append(
                    {
                        "ticker": ticker,
                        "gap_type": "internal_missing_yahoo_period",
                        "previous_period_end": left_end.date().isoformat(),
                        "next_period_end": right_end.date().isoformat(),
                        "gap_days": gap_days,
                        "estimated_missing_quarters": estimated,
                        "detail": "Yahoo diluted TTM har en lucka mellan två observerade perioder.",
                    }
                )

        missing_dates = group.loc[group["report_date"].isna()]
        for row in missing_dates.itertuples(index=False):
            period_end = pd.Timestamp(row.period_end)
            is_first = period_end == pd.Timestamp(first["period_end"])
            is_last = period_end == pd.Timestamp(last["period_end"])
            if is_first:
                position = "leading"
            elif is_last:
                position = "trailing"
            else:
                position = "internal"
            rows.append(
                {
                    "ticker": ticker,
                    "gap_type": f"{position}_missing_report_date",
                    "previous_period_end": period_end.date().isoformat(),
                    "next_period_end": "",
                    "gap_days": pd.NA,
                    "estimated_missing_quarters": pd.NA,
                    "detail": "EPS-värdet finns hos Yahoo men kan inte aktiveras historiskt utan säkert rapportdatum.",
                }
            )
    return pd.DataFrame(rows)


def audit(
    alignment_file: Path = ALIGNMENT_FILE,
    yahoo_history_file: Path = YAHOO_HISTORY_FILE,
    reference_output: Path = REFERENCE_GAPS_FILE,
    continuity_output: Path = CONTINUITY_FILE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    reference = _audit_reference_gaps(alignment_file)
    continuity = _audit_yahoo_continuity(yahoo_history_file)

    reference_output.parent.mkdir(parents=True, exist_ok=True)
    continuity_output.parent.mkdir(parents=True, exist_ok=True)
    reference.to_csv(reference_output, index=False)
    continuity.to_csv(continuity_output, index=False)

    if reference.empty:
        print("Inga referens-fallbacks finns i den första historikbatchen.")
    else:
        counts = reference["gap_position"].value_counts().to_dict()
        print(f"Referensluckor: {len(reference)} totalt; positioner {counts}.")
        internal = reference.loc[reference["gap_position"] == "internal"]
        if not internal.empty:
            print("Interna luckor där Börsdata kan användas som kontrollreferens:")
            print(
                internal[
                    ["ticker", "report_period", "report_date", "previous_comparable_period", "next_comparable_period", "stale_window_days"]
                ].to_string(index=False)
            )

    internal_yahoo = continuity.loc[continuity["gap_type"] == "internal_missing_yahoo_period"] if not continuity.empty else continuity
    missing_date_internal = continuity.loc[continuity["gap_type"] == "internal_missing_report_date"] if not continuity.empty else continuity
    print(
        f"Hela Yahoo-universumet: {len(internal_yahoo)} interna periodluckor och "
        f"{len(missing_date_internal)} interna perioder utan säkert rapportdatum."
    )
    return reference, continuity


if __name__ == "__main__":
    audit()
