from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT
from .fetch_data import load_price_history

HISTORY_FILE = ROOT / "data" / "fundamentals" / "yahoo_history_all.csv"
OUTPUT_FILE = ROOT / "data" / "derived" / "yahoo_eps_startpoints.csv"


def _quarter_label(value: pd.Timestamp | pd.NaT) -> str:
    if pd.isna(value):
        return ""
    value = pd.Timestamp(value)
    return f"{value.year}-Q{((value.month - 1) // 3) + 1}"


def audit(
    history_file: Path = HISTORY_FILE,
    output_file: Path = OUTPUT_FILE,
) -> pd.DataFrame:
    prices = load_price_history()
    universe = pd.DataFrame(
        {"ticker": sorted(prices["ticker"].dropna().astype(str).str.strip().unique())}
    )
    if len(universe) != 119:
        print(f"VARNING: prisuniversumet innehåller {len(universe)} tickers, inte 119.")

    history = pd.read_csv(history_file, encoding="utf-8-sig")
    required = {"ticker", "period_end", "report_date", "eps_ttm", "alignment_status"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"Yahoo-historiken saknar kolumner: {', '.join(sorted(missing))}")

    history = history.copy()
    history["ticker"] = history["ticker"].astype(str).str.strip()
    history["period_end"] = pd.to_datetime(history["period_end"], errors="coerce")
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce")
    history["eps_ttm"] = pd.to_numeric(history["eps_ttm"], errors="coerce")
    history = history.dropna(subset=["ticker", "period_end", "eps_ttm"])

    rows: list[dict[str, object]] = []
    for ticker in universe["ticker"]:
        group = history.loc[history["ticker"] == ticker].sort_values("period_end").copy()
        if group.empty:
            rows.append(
                {
                    "ticker": ticker,
                    "earliest_eps_period_end": "",
                    "earliest_eps_quarter": "",
                    "earliest_usable_period_end": "",
                    "earliest_usable_quarter": "",
                    "earliest_usable_report_date": "",
                    "periods_with_eps": 0,
                    "periods_with_report_date": 0,
                    "periods_before_first_usable": 0,
                    "start_status": "no_yahoo_eps_history",
                }
            )
            continue

        earliest_eps = pd.Timestamp(group.iloc[0]["period_end"])
        usable = group.loc[group["report_date"].notna()].sort_values("period_end")
        if usable.empty:
            earliest_usable = pd.NaT
            earliest_report = pd.NaT
            before_usable = len(group)
            status = "eps_exists_but_no_report_date"
        else:
            first = usable.iloc[0]
            earliest_usable = pd.Timestamp(first["period_end"])
            earliest_report = pd.Timestamp(first["report_date"])
            before_usable = int((group["period_end"] < earliest_usable).sum())
            status = "usable"

        rows.append(
            {
                "ticker": ticker,
                "earliest_eps_period_end": earliest_eps.date().isoformat(),
                "earliest_eps_quarter": _quarter_label(earliest_eps),
                "earliest_usable_period_end": earliest_usable.date().isoformat() if pd.notna(earliest_usable) else "",
                "earliest_usable_quarter": _quarter_label(earliest_usable),
                "earliest_usable_report_date": earliest_report.date().isoformat() if pd.notna(earliest_report) else "",
                "periods_with_eps": len(group),
                "periods_with_report_date": int(group["report_date"].notna().sum()),
                "periods_before_first_usable": before_usable,
                "start_status": status,
            }
        )

    result = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)

    usable = result.loc[result["start_status"] == "usable"].copy()
    print(f"Yahoo startpunkter: {len(usable)}/{len(result)} tickers har EPS + säkert rapportdatum.")
    if not usable.empty:
        print("Fördelning av första användbara kvartal:")
        print(usable["earliest_usable_quarter"].value_counts().sort_index().to_string())
        print("Startpunkt per ticker:")
        print(
            usable[
                ["ticker", "earliest_usable_period_end", "earliest_usable_report_date"]
            ].to_string(index=False)
        )
    missing_dates = result.loc[result["start_status"] == "eps_exists_but_no_report_date", "ticker"].tolist()
    if missing_dates:
        print("EPS finns men säkert rapportdatum saknas för:", ", ".join(missing_dates))
    return result


if __name__ == "__main__":
    audit()
