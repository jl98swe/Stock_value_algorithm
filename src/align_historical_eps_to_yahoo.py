from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
YAHOO_TIMESERIES_FILE = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
OUTPUT_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_aligned.csv"
AUDIT_FILE = ROOT / "data" / "derived" / "eps_alignment_audit.csv"
MAX_PERIOD_END_TO_REPORT_DAYS = 100
YAHOO_SOURCE = "Yahoo Finance / trailingDilutedEPS historical timeseries"
FALLBACK_SOURCE = "User-supplied historical EPS TTM fallback"


def _pct_diff(new: float, old: float) -> float:
    denominator = max(abs(float(old)), 1e-9)
    return abs(float(new) - float(old)) / denominator * 100.0


def _load_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Historisk EPS saknar kolumner: {', '.join(missing)}")
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["report_period"] = result["report_period"].astype(str).str.strip()
    result["report_date"] = pd.to_datetime(result["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["currency"] = result["currency"].astype(str).str.strip().str.upper()
    result = result.dropna(subset=required).copy()
    if result.duplicated(["ticker", "report_period"]).any():
        raise ValueError("Historisk EPS innehåller dubbla ticker + report_period")
    return result.sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)


def _load_yahoo(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = ["ticker", "metric", "as_of_date", "value", "currency_code"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Yahoo-timeseries saknar kolumner: {', '.join(missing)}")
    result = frame.loc[frame["metric"] == "trailingDilutedEPS", required].copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["as_of_date"] = pd.to_datetime(result["as_of_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["currency_code"] = result["currency_code"].astype(str).str.strip().str.upper()
    result = result.dropna(subset=["ticker", "as_of_date", "value"]).copy()
    return (
        result.sort_values(["ticker", "as_of_date"])
        .drop_duplicates(["ticker", "as_of_date"], keep="last")
        .reset_index(drop=True)
    )


def _map_ticker(history: pd.DataFrame, yahoo: pd.DataFrame) -> dict[int, pd.Series]:
    """Matcha varje rapport mot senaste unika Yahoo-periodslut före rapportdagen.

    Mappingen görs bakifrån så att samma Yahoo-period aldrig kan återanvändas för
    två rapporter. Ett periodslut längre än 100 dagar före rapportdagen accepteras
    inte; då behålls den uppladdade historiska raden som fallback i stället för att
    riskera en kvartalsförskjutning.
    """
    mapping: dict[int, pd.Series] = {}
    if yahoo.empty:
        return mapping

    upper_bound: pd.Timestamp | None = None
    for idx, row in history.sort_values("report_date", ascending=False).iterrows():
        candidates = yahoo.loc[yahoo["as_of_date"] < row["report_date"]].copy()
        if upper_bound is not None:
            candidates = candidates.loc[candidates["as_of_date"] < upper_bound]
        if candidates.empty:
            continue
        best = candidates.sort_values("as_of_date").iloc[-1]
        lag_days = int((pd.Timestamp(row["report_date"]) - pd.Timestamp(best["as_of_date"])).days)
        if lag_days < 0 or lag_days > MAX_PERIOD_END_TO_REPORT_DAYS:
            continue
        mapping[int(idx)] = best
        upper_bound = pd.Timestamp(best["as_of_date"])
    return mapping


def align(
    history_file: Path = HISTORY_FILE,
    yahoo_file: Path = YAHOO_TIMESERIES_FILE,
    output_file: Path = OUTPUT_FILE,
    audit_file: Path = AUDIT_FILE,
) -> pd.DataFrame:
    history = _load_history(history_file)
    yahoo = _load_yahoo(yahoo_file)

    aligned_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []

    for ticker, ticker_history in history.groupby("ticker", sort=True):
        ticker_yahoo = yahoo.loc[yahoo["ticker"] == ticker].copy()
        mapping = _map_ticker(ticker_history, ticker_yahoo)
        for idx, row in ticker_history.iterrows():
            original_eps = float(row["eps_ttm"])
            original_currency = str(row["currency"]).upper()
            mapped = mapping.get(int(idx))

            if mapped is not None:
                yahoo_currency = str(mapped["currency_code"]).upper() or original_currency
                if yahoo_currency and yahoo_currency != original_currency:
                    raise ValueError(
                        f"Yahoo trailingDilutedEPS-valuta avviker för {ticker} {row['report_period']}: "
                        f"{yahoo_currency} != {original_currency}"
                    )
                eps_ttm = float(mapped["value"])
                period_end = pd.Timestamp(mapped["as_of_date"])
                source = YAHOO_SOURCE
                status = "yahoo_trailing_diluted"
                lag_days = int((pd.Timestamp(row["report_date"]) - period_end).days)
            else:
                eps_ttm = original_eps
                period_end = pd.NaT
                source = FALLBACK_SOURCE
                status = "fallback_user_history"
                lag_days = np.nan

            aligned_rows.append(
                {
                    "ticker": ticker,
                    "report_period": row["report_period"],
                    "period_end": period_end.date().isoformat() if pd.notna(period_end) else "",
                    "report_date": pd.Timestamp(row["report_date"]).date().isoformat(),
                    "eps_ttm": eps_ttm,
                    "currency": original_currency,
                    "eps_source": source,
                    "alignment_status": status,
                }
            )
            audit_rows.append(
                {
                    "ticker": ticker,
                    "report_period": row["report_period"],
                    "report_date": pd.Timestamp(row["report_date"]).date().isoformat(),
                    "period_end": period_end.date().isoformat() if pd.notna(period_end) else "",
                    "period_end_to_report_days": lag_days,
                    "original_eps_ttm": original_eps,
                    "aligned_eps_ttm": eps_ttm,
                    "currency": original_currency,
                    "abs_change_pct": _pct_diff(eps_ttm, original_eps),
                    "alignment_status": status,
                    "eps_source": source,
                }
            )

    aligned = pd.DataFrame(aligned_rows).sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)
    audit = pd.DataFrame(audit_rows).sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(output_file, index=False)
    audit.to_csv(audit_file, index=False)

    yahoo_rows = int((aligned["alignment_status"] == "yahoo_trailing_diluted").sum())
    fallback_rows = len(aligned) - yahoo_rows
    fallback_tickers = int(aligned.loc[aligned["alignment_status"] != "yahoo_trailing_diluted", "ticker"].nunique())
    materially_changed = int((audit["abs_change_pct"] > 5.0).sum())
    print(
        f"Historisk EPS alignad mot Yahoo trailingDilutedEPS: {yahoo_rows}/{len(aligned)} rader direkt från Yahoo; "
        f"{fallback_rows} fallback-rader i {fallback_tickers} tickers; {materially_changed} rader ändrades >5%."
    )
    if fallback_rows:
        print("Fallback-rader:")
        print(
            aligned.loc[aligned["alignment_status"] != "yahoo_trailing_diluted", ["ticker", "report_period", "report_date", "eps_ttm"]]
            .to_string(index=False)
        )
    return aligned


if __name__ == "__main__":
    align()
