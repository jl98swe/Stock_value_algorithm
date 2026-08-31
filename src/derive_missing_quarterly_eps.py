from __future__ import annotations

import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ROOT
from .quarterly_eps import (
    DILUTED_METRIC,
    QUARTERLY_COLUMNS,
    _publish_json,
    load_quarterly_eps,
    save_quarterly_eps,
)

AUDIT_FILE = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
SOURCE = "Yahoo Finance / derived from trailingDilutedEPS and prior quarterlyDilutedEPS"
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
MAX_PERIOD_GAP_DAYS = 150
MIN_WINDOW_SPAN_DAYS = 230
MAX_WINDOW_SPAN_DAYS = 380


def _safe_diluted_rows(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["period_end"] = pd.to_datetime(data["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["eps"] = pd.to_numeric(data["eps"], errors="coerce")
    data["eps_currency"] = data["eps_currency"].fillna("").astype(str).str.strip().str.upper()
    return data.loc[
        (data["metric"].astype(str) == DILUTED_METRIC)
        & data["period_end"].notna()
        & data["eps"].notna()
    ].copy()


def derive_missing_quarters() -> pd.DataFrame:
    if not AUDIT_FILE.exists() or AUDIT_FILE.stat().st_size == 0:
        raise FileNotFoundError(f"Saknar {AUDIT_FILE}")

    audit = pd.read_csv(AUDIT_FILE)
    required = {"ticker", "metric", "as_of_date", "value", "currency_code"}
    missing_columns = sorted(required.difference(audit.columns))
    if missing_columns:
        raise ValueError(f"Yahoo-audit saknar kolumner: {', '.join(missing_columns)}")

    trailing = audit.loc[audit["metric"].astype(str) == "trailingDilutedEPS"].copy()
    trailing["as_of_date"] = pd.to_datetime(trailing["as_of_date"], errors="coerce").dt.normalize()
    trailing["value"] = pd.to_numeric(trailing["value"], errors="coerce")
    trailing["currency_code"] = trailing["currency_code"].fillna("").astype(str).str.strip().str.upper()
    trailing = trailing.dropna(subset=["ticker", "as_of_date", "value"])

    existing = load_quarterly_eps()
    working = _safe_diluted_rows(existing)
    observed_date = datetime.now(STOCKHOLM_TZ).date().isoformat()
    derived_rows: list[dict[str, object]] = []

    for ticker, ticker_trailing in trailing.groupby("ticker", sort=True):
        series = (
            ticker_trailing.sort_values("as_of_date")
            .drop_duplicates("as_of_date", keep="last")
            .reset_index(drop=True)
        )
        ticker_working = working.loc[working["ticker"].astype(str) == str(ticker)].copy()

        for index in range(3, len(series)):
            current = series.iloc[index]
            current_period = pd.Timestamp(current["as_of_date"]).normalize()
            if (ticker_working["period_end"] == current_period).any():
                continue

            previous_periods = [pd.Timestamp(series.iloc[pos]["as_of_date"]).normalize() for pos in range(index - 3, index)]
            all_periods = previous_periods + [current_period]
            gaps = [int((right - left).days) for left, right in zip(all_periods, all_periods[1:], strict=False)]
            span_days = int((current_period - previous_periods[0]).days)
            if not gaps or max(gaps) > MAX_PERIOD_GAP_DAYS:
                continue
            if span_days < MIN_WINDOW_SPAN_DAYS or span_days > MAX_WINDOW_SPAN_DAYS:
                continue

            components: list[pd.Series] = []
            for period in previous_periods:
                candidates = ticker_working.loc[ticker_working["period_end"] == period].copy()
                if candidates.empty:
                    components = []
                    break
                candidates["manual_priority"] = (
                    candidates["source"].astype(str).str.contains("manuell|manual", case=False, regex=True).map({True: 0, False: 1})
                )
                components.append(candidates.sort_values(["manual_priority", "observed_date"]).iloc[-1])
            if len(components) != 3:
                continue

            trailing_currency = str(current["currency_code"] or "").strip().upper()
            component_currencies = {str(row["eps_currency"] or "").strip().upper() for row in components}
            component_currencies.discard("")
            if len(component_currencies) > 1:
                continue
            component_currency = next(iter(component_currencies), "")
            if trailing_currency and component_currency and trailing_currency != component_currency:
                continue
            currency = trailing_currency or component_currency
            if not currency:
                continue

            trailing_value = float(current["value"])
            component_sum = sum(float(row["eps"]) for row in components)
            derived_eps = trailing_value - component_sum
            if not math.isfinite(derived_eps):
                continue

            row = {
                "ticker": str(ticker),
                "period_end": current_period,
                "report_date": pd.NaT,
                "observed_date": observed_date,
                "metric": DILUTED_METRIC,
                "eps": float(derived_eps),
                "eps_currency": currency,
                "source": SOURCE,
            }
            derived_rows.append(row)
            ticker_working = pd.concat(
                [ticker_working, pd.DataFrame([row], columns=QUARTERLY_COLUMNS)],
                ignore_index=True,
            )
            ticker_working = _safe_diluted_rows(ticker_working)

    if not derived_rows:
        print("Yahoo derived diluted EPS: inga nya perioder kunde eller behövde härledas.")
        return existing

    derived = pd.DataFrame(derived_rows, columns=QUARTERLY_COLUMNS)
    combined = pd.concat([existing, derived], ignore_index=True)
    save_quarterly_eps(combined)
    saved = load_quarterly_eps()
    _publish_json(saved)

    audit_output = {
        "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
        "derived_periods": len(derived),
        "derived_tickers": int(derived["ticker"].nunique()),
        "source": SOURCE,
        "formula": "quarterlyDilutedEPS = trailingDilutedEPS - sum(previous three quarterlyDilutedEPS)",
    }
    out = ROOT / "data" / "derived" / "quarterly_eps_derived_summary.json"
    out.write_text(json.dumps(audit_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Yahoo derived diluted EPS: härledde {len(derived)} saknade perioder "
        f"för {derived['ticker'].nunique()} tickers."
    )
    return saved


def main() -> None:
    derive_missing_quarters()


if __name__ == "__main__":
    main()
