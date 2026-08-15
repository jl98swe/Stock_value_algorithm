from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
OVERRIDES_FILE = ROOT / "data" / "fundamentals" / "report_date_overrides.csv"
MISSING_FILE = ROOT / "data" / "derived" / "eps_report_date_missing.csv"
APPLIED_FILE = ROOT / "data" / "derived" / "eps_report_date_overrides_applied.csv"

OVERRIDE_COLUMNS = ["ticker", "report_period", "report_date", "source"]


def apply_overrides(
    history_file: Path = HISTORY_FILE,
    overrides_file: Path = OVERRIDES_FILE,
    missing_file: Path = MISSING_FILE,
    applied_file: Path = APPLIED_FILE,
) -> pd.DataFrame:
    history = pd.read_csv(history_file, encoding="utf-8-sig")
    overrides = pd.read_csv(overrides_file, encoding="utf-8-sig")

    required_history = {"ticker", "report_period", "report_date", "eps_ttm", "currency"}
    missing_columns = sorted(required_history.difference(history.columns))
    if missing_columns:
        raise ValueError(f"Historikfilen saknar kolumner: {', '.join(missing_columns)}")

    missing_override_columns = [column for column in OVERRIDE_COLUMNS if column not in overrides.columns]
    if missing_override_columns:
        raise ValueError(f"Override-filen saknar kolumner: {', '.join(missing_override_columns)}")

    history["ticker"] = history["ticker"].astype(str).str.strip()
    history["report_period"] = history["report_period"].astype(str).str.strip()
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce")

    overrides = overrides[OVERRIDE_COLUMNS].copy()
    if not overrides.empty:
        overrides["ticker"] = overrides["ticker"].astype(str).str.strip()
        overrides["report_period"] = overrides["report_period"].astype(str).str.strip()
        overrides["report_date"] = pd.to_datetime(overrides["report_date"], errors="coerce")
        overrides["source"] = overrides["source"].astype(str).str.strip()
        if overrides[["ticker", "report_period", "report_date", "source"]].isna().any().any():
            raise ValueError("Override-filen innehåller saknad ticker, period, datum eller källa")
        if overrides.duplicated(["ticker", "report_period"]).any():
            raise ValueError("Override-filen innehåller dubbla ticker + report_period")

    history_keys = set(zip(history["ticker"], history["report_period"], strict=False))
    applied_rows: list[dict[str, object]] = []
    for row in overrides.itertuples(index=False):
        key = (str(row.ticker), str(row.report_period))
        if key not in history_keys:
            raise ValueError(f"Override saknar matchande EPS-rad: {key[0]} {key[1]}")
        mask = (history["ticker"] == key[0]) & (history["report_period"] == key[1])
        old = history.loc[mask, "report_date"].iloc[0]
        new = pd.Timestamp(row.report_date).normalize()
        history.loc[mask, "report_date"] = new
        applied_rows.append(
            {
                "ticker": key[0],
                "report_period": key[1],
                "previous_report_date": old.date().isoformat() if pd.notna(old) else "",
                "report_date": new.date().isoformat(),
                "source": row.source,
            }
        )

    history = history.sort_values(["ticker", "report_period"]).reset_index(drop=True)
    history["report_date"] = history["report_date"].dt.strftime("%Y-%m-%d")
    history.to_csv(history_file, index=False)

    missing = history.loc[history["report_date"].isna() | history["report_date"].eq("")].copy()
    missing_file.parent.mkdir(parents=True, exist_ok=True)
    missing.to_csv(missing_file, index=False)

    applied = pd.DataFrame(
        applied_rows,
        columns=["ticker", "report_period", "previous_report_date", "report_date", "source"],
    )
    applied_file.parent.mkdir(parents=True, exist_ok=True)
    applied.to_csv(applied_file, index=False)

    print(
        f"Rapportdatum-overrides: {len(applied)} applicerade. "
        f"Återstår {len(missing)} EPS-rader utan rapportdatum."
    )
    return history


if __name__ == "__main__":
    apply_overrides()
