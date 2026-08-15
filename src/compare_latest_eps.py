from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .earnings import EPS_METRIC, latest_earnings

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_aligned.csv"
OUTPUT_FILE = ROOT / "data" / "derived" / "latest_eps_yahoo_comparison.csv"
MATCH_TOLERANCE_PCT = 1.0
NEAR_TOLERANCE_PCT = 5.0


def _relative_error_pct(actual: float, expected: float) -> float:
    denominator = max(abs(float(expected)), 1e-9)
    return abs(float(actual) - float(expected)) / denominator * 100.0


def compare(
    history_file: Path = HISTORY_FILE,
    output_file: Path = OUTPUT_FILE,
) -> pd.DataFrame:
    history = pd.read_csv(history_file, encoding="utf-8-sig")
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    history["period_end"] = pd.to_datetime(history.get("period_end"), errors="coerce").dt.tz_localize(None).dt.normalize()
    history["eps_ttm"] = pd.to_numeric(history["eps_ttm"], errors="coerce")
    history["currency"] = history["currency"].astype(str).str.strip().str.upper()
    history = history.dropna(subset=["ticker", "report_date", "eps_ttm"]).copy()

    yahoo = latest_earnings()
    if yahoo.empty:
        raise ValueError("Yahoo EPS-snapshot är tom. Kör python -m src.earnings först.")

    rows: list[dict[str, object]] = []
    for current in yahoo.itertuples(index=False):
        ticker = str(current.ticker)
        yahoo_period_end = pd.Timestamp(current.period_end).normalize() if pd.notna(current.period_end) else pd.NaT
        yahoo_report_date = pd.Timestamp(current.report_date).normalize() if pd.notna(current.report_date) else pd.NaT
        yahoo_eps = float(current.eps_ttm)
        yahoo_currency = str(current.eps_currency or "").strip().upper()

        candidates = history.loc[history["ticker"].astype(str) == ticker].copy()
        if pd.notna(yahoo_period_end):
            same_period = candidates.loc[candidates["period_end"].notna() & (candidates["period_end"] == yahoo_period_end)]
        else:
            same_period = pd.DataFrame(columns=candidates.columns)

        matched = same_period.sort_values("report_date").iloc[-1] if not same_period.empty else None
        if matched is None:
            rows.append(
                {
                    "ticker": ticker,
                    "report_period": "",
                    "period_end": yahoo_period_end.date().isoformat() if pd.notna(yahoo_period_end) else "",
                    "historical_report_date": "",
                    "yahoo_report_date": yahoo_report_date.date().isoformat() if pd.notna(yahoo_report_date) else "",
                    "report_date_delta_days": np.nan,
                    "report_date_status": "no_same_period_history",
                    "historical_eps_ttm": np.nan,
                    "historical_currency": "",
                    "yahoo_eps_ttm": yahoo_eps,
                    "yahoo_eps_currency": yahoo_currency,
                    "error_pct": np.nan,
                    "value_status": "no_same_period_history",
                    "historical_alignment_status": "",
                    "yahoo_observed_date": pd.Timestamp(current.observed_date).date().isoformat(),
                }
            )
            continue

        historical_eps = float(matched["eps_ttm"])
        historical_currency = str(matched["currency"]).strip().upper()
        if yahoo_currency != historical_currency:
            error = np.nan
            status = "currency_mismatch"
        else:
            error = _relative_error_pct(yahoo_eps, historical_eps)
            if error <= MATCH_TOLERANCE_PCT:
                status = "match"
            elif error <= NEAR_TOLERANCE_PCT:
                status = "near"
            else:
                status = "mismatch"

        historical_report_date = pd.Timestamp(matched["report_date"]).normalize()
        date_delta = abs((yahoo_report_date - historical_report_date).days) if pd.notna(yahoo_report_date) else np.nan
        date_status = (
            "match" if pd.notna(date_delta) and int(date_delta) == 0
            else "near" if pd.notna(date_delta) and int(date_delta) <= 3
            else "mismatch" if pd.notna(date_delta)
            else "missing_yahoo"
        )

        rows.append(
            {
                "ticker": ticker,
                "report_period": matched["report_period"],
                "period_end": yahoo_period_end.date().isoformat() if pd.notna(yahoo_period_end) else "",
                "historical_report_date": historical_report_date.date().isoformat(),
                "yahoo_report_date": yahoo_report_date.date().isoformat() if pd.notna(yahoo_report_date) else "",
                "report_date_delta_days": date_delta,
                "report_date_status": date_status,
                "historical_eps_ttm": historical_eps,
                "historical_currency": historical_currency,
                "yahoo_eps_ttm": yahoo_eps,
                "yahoo_eps_currency": yahoo_currency,
                "error_pct": error,
                "value_status": status,
                "historical_alignment_status": str(matched.get("alignment_status", "")),
                "yahoo_observed_date": pd.Timestamp(current.observed_date).date().isoformat(),
            }
        )

    result = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)

    comparable = result["value_status"].isin(["match", "near", "mismatch"])
    matches = result["value_status"].isin(["match", "near"])
    print(
        f"Yahoo {EPS_METRIC}-jämförelse: {int(comparable.sum())}/{len(result)} har samma historiska period; "
        f"{int(matches.sum())}/{int(comparable.sum()) if comparable.any() else 0} jämförbara ligger inom "
        f"{NEAR_TOLERANCE_PCT:.0f}% i samma valuta."
    )
    mismatches = result.loc[result["value_status"].isin(["mismatch", "currency_mismatch"])]
    if not mismatches.empty:
        print("Avvikelser:")
        print(
            mismatches[[
                "ticker", "period_end", "historical_eps_ttm", "historical_currency",
                "yahoo_eps_ttm", "yahoo_eps_currency", "error_pct", "value_status"
            ]].to_string(index=False)
        )
    return result


if __name__ == "__main__":
    compare()
