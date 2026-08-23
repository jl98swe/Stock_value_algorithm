from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history.csv"
UPDATES_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_manual_updates.csv"
COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]


def main() -> None:
    history = pd.read_csv(HISTORY_FILE, encoding="utf-8-sig")
    updates = pd.read_csv(UPDATES_FILE, encoding="utf-8-sig")

    for frame, label in ((history, "eps_ttm_history.csv"), (updates, "eps_ttm_history_manual_updates.csv")):
        missing = [column for column in COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"{label} saknar kolumner: {', '.join(missing)}")

    history = history[COLUMNS].copy()
    updates = updates[COLUMNS].copy()

    for frame in (history, updates):
        frame["ticker"] = frame["ticker"].astype(str).str.strip()
        frame["report_period"] = frame["report_period"].astype(str).str.strip()
        frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
        frame["eps_ttm"] = pd.to_numeric(frame["eps_ttm"], errors="coerce")
        frame["currency"] = frame["currency"].astype(str).str.strip().str.upper()

    if updates[["ticker", "report_period", "eps_ttm", "currency"]].isna().any().any():
        raise ValueError("Manuella EPS-uppdateringar innehåller saknade obligatoriska värden")
    if updates.duplicated(["ticker", "report_period"]).any():
        raise ValueError("Manuella EPS-uppdateringar innehåller dubbla ticker + report_period")

    update_keys = pd.MultiIndex.from_frame(updates[["ticker", "report_period"]])
    history_keys = pd.MultiIndex.from_frame(history[["ticker", "report_period"]])
    history = history.loc[~history_keys.isin(update_keys)].copy()

    merged = pd.concat([history, updates], ignore_index=True)
    merged = merged.sort_values(["ticker", "report_period"]).reset_index(drop=True)
    merged["report_date"] = merged["report_date"].dt.strftime("%Y-%m-%d").fillna("")

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
    print(f"Applicerade {len(updates)} manuella EPS-rader i {HISTORY_FILE}")


if __name__ == "__main__":
    main()
