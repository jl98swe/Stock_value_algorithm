from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ROOT
from .fetch_data import load_price_history
from .quarterly_eps import DILUTED_METRIC, MANUAL_METRIC, load_quarterly_eps

OUT_CSV = ROOT / "data" / "derived" / "quarterly_eps_readiness.csv"
OUT_JSON = ROOT / "data" / "derived" / "quarterly_eps_readiness_summary.json"
TRAILING_AUDIT = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
NON_QUARTERLY_TICKERS = {"EQT.ST"}
MAX_COMPARABLE_DISTANCE_DAYS = 21
SAFE_METRICS = {DILUTED_METRIC, MANUAL_METRIC}


def _universe() -> list[str]:
    prices = load_price_history()
    return sorted(prices["ticker"].dropna().astype(str).str.strip().unique().tolist())


def _next_period(period_end: pd.Timestamp) -> pd.Timestamp:
    period = pd.Timestamp(period_end).normalize()
    target = period + pd.DateOffset(months=3)
    if period.is_month_end:
        target = target + pd.offsets.MonthEnd(0)
    return pd.Timestamp(target).normalize()


def _prior_year(period_end: pd.Timestamp) -> pd.Timestamp:
    period = pd.Timestamp(period_end).normalize()
    target = period - pd.DateOffset(years=1)
    if period.is_month_end:
        target = target + pd.offsets.MonthEnd(0)
    return pd.Timestamp(target).normalize()


def audit_readiness(*, fail_on_missing: bool = True) -> tuple[pd.DataFrame, dict[str, object]]:
    if not TRAILING_AUDIT.exists() or TRAILING_AUDIT.stat().st_size == 0:
        raise FileNotFoundError(f"Saknar {TRAILING_AUDIT}")

    trailing = pd.read_csv(TRAILING_AUDIT)
    trailing = trailing.loc[trailing["metric"].astype(str) == "trailingDilutedEPS"].copy()
    trailing["as_of_date"] = pd.to_datetime(trailing["as_of_date"], errors="coerce").dt.normalize()
    trailing["value"] = pd.to_numeric(trailing["value"], errors="coerce")
    trailing["currency_code"] = trailing["currency_code"].fillna("").astype(str).str.strip().str.upper()
    trailing = trailing.dropna(subset=["ticker", "as_of_date", "value"])

    eps = load_quarterly_eps()
    eps = eps.loc[eps["metric"].astype(str).isin(SAFE_METRICS)].copy()
    eps["period_end"] = pd.to_datetime(eps["period_end"], errors="coerce").dt.normalize()
    eps["eps"] = pd.to_numeric(eps["eps"], errors="coerce")
    eps["eps_currency"] = eps["eps_currency"].fillna("").astype(str).str.strip().str.upper()
    eps = eps.dropna(subset=["ticker", "period_end", "eps"])

    rows: list[dict[str, object]] = []
    for ticker in _universe():
        non_quarterly = ticker in NON_QUARTERLY_TICKERS
        ticker_ttm = trailing.loc[trailing["ticker"].astype(str) == ticker].sort_values("as_of_date")
        ticker_eps = eps.loc[eps["ticker"].astype(str) == ticker].copy()

        latest_ttm_period = pd.NaT
        latest_ttm = None
        ttm_currency = ""
        next_period = pd.NaT
        comparable_target = pd.NaT
        comparable_period = pd.NaT
        comparable_eps = None
        comparable_currency = ""
        comparable_metric = ""
        comparable_source = ""
        reason = ""

        if non_quarterly:
            ready = True
            reason = "Bolaget hanteras som icke-kvartalsrapporterande; ingen Q1/Q3-EPS konstrueras."
        elif ticker_ttm.empty:
            ready = False
            reason = "Saknar Yahoo trailingDilutedEPS."
        else:
            latest = ticker_ttm.iloc[-1]
            latest_ttm_period = pd.Timestamp(latest["as_of_date"]).normalize()
            latest_ttm = float(latest["value"])
            ttm_currency = str(latest["currency_code"] or "").strip().upper()
            next_period = _next_period(latest_ttm_period)
            comparable_target = _prior_year(next_period)

            if ticker_eps.empty:
                ready = False
                reason = "Saknar sparad diluted EPS-historik."
            else:
                ticker_eps["distance_days"] = (ticker_eps["period_end"] - comparable_target).abs().dt.days
                candidates = ticker_eps.loc[
                    ticker_eps["distance_days"] <= MAX_COMPARABLE_DISTANCE_DAYS
                ].copy()
                if candidates.empty:
                    ready = False
                    reason = "Saknar diluted EPS för motsvarande rapportperiod föregående år."
                else:
                    candidates["manual_priority"] = (candidates["metric"] == MANUAL_METRIC).map({True: 0, False: 1})
                    match = candidates.sort_values(["distance_days", "manual_priority", "observed_date"]).iloc[0]
                    comparable_period = pd.Timestamp(match["period_end"]).normalize()
                    comparable_eps = float(match["eps"])
                    comparable_currency = str(match["eps_currency"] or "").strip().upper()
                    comparable_metric = str(match["metric"])
                    comparable_source = str(match["source"])
                    currency_ok = bool(ttm_currency and comparable_currency and ttm_currency == comparable_currency)
                    ready = currency_ok
                    reason = (
                        "Redo: senaste Yahoo-TTM och jämförbar diluted EPS finns i samma valuta."
                        if ready
                        else f"Valutakonflikt eller saknad valuta: TTM={ttm_currency or 'NA'}, EPS={comparable_currency or 'NA'}."
                    )

        rows.append(
            {
                "ticker": ticker,
                "reporting_mode": "non_quarterly" if non_quarterly else "quarterly",
                "latest_ttm_period": latest_ttm_period.date().isoformat() if pd.notna(latest_ttm_period) else "",
                "latest_ttm": latest_ttm,
                "ttm_currency": ttm_currency,
                "next_manual_period": next_period.date().isoformat() if pd.notna(next_period) else "",
                "prior_year_target": comparable_target.date().isoformat() if pd.notna(comparable_target) else "",
                "comparable_period": comparable_period.date().isoformat() if pd.notna(comparable_period) else "",
                "comparable_eps": comparable_eps,
                "comparable_currency": comparable_currency,
                "comparable_metric": comparable_metric,
                "comparable_source": comparable_source,
                "ready_for_single_eps_input": bool(ready),
                "reason": reason,
            }
        )

    frame = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    quarterly = frame.loc[frame["reporting_mode"] == "quarterly"]
    missing = quarterly.loc[~quarterly["ready_for_single_eps_input"].astype(bool), "ticker"].astype(str).tolist()
    summary: dict[str, object] = {
        "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
        "universe_tickers": int(len(frame)),
        "quarterly_tickers": int(len(quarterly)),
        "non_quarterly_tickers": sorted(NON_QUARTERLY_TICKERS.intersection(set(frame["ticker"].astype(str)))),
        "quarterly_ready": int(quarterly["ready_for_single_eps_input"].astype(bool).sum()),
        "quarterly_not_ready": int(len(missing)),
        "not_ready_tickers": missing,
        "criterion": (
            "For the next quarterly report after the latest Yahoo trailingDilutedEPS period: "
            "a comparable manualDilutedEPS/quarterlyDilutedEPS period one year earlier must exist "
            "within 21 days and use the same non-empty report currency."
        ),
    }

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"Single-EPS readiness: {summary['quarterly_ready']}/{summary['quarterly_tickers']} "
        "kvartalsrapporterande tickers redo."
    )
    if missing:
        print("Inte redo: " + ", ".join(missing))
        if fail_on_missing:
            raise RuntimeError("Saknar säkert single-EPS-underlag för: " + ", ".join(missing))
    return frame, summary


def main() -> None:
    audit_readiness(fail_on_missing=True)


if __name__ == "__main__":
    main()
