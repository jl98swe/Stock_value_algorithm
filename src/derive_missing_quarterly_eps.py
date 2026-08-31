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
SOURCE = "Yahoo Finance / derived from trailingDilutedEPS and quarterlyDilutedEPS"
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
MAX_PERIOD_GAP_DAYS = 150
MIN_WINDOW_SPAN_DAYS = 230
MAX_WINDOW_SPAN_DAYS = 380
MIN_DOUBLE_QUARTER_GAP_DAYS = 150
MAX_DOUBLE_QUARTER_GAP_DAYS = 220
MAX_SINGLE_QUARTER_GAP_DAYS = 120


def _safe_diluted_rows(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["period_end"] = pd.to_datetime(data["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["observed_date"] = pd.to_datetime(data["observed_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["eps"] = pd.to_numeric(data["eps"], errors="coerce")
    data["eps_currency"] = data["eps_currency"].fillna("").astype(str).str.strip().str.upper()
    return data.loc[
        (data["metric"].astype(str) == DILUTED_METRIC)
        & data["period_end"].notna()
        & data["eps"].notna()
    ].copy()


def _select_component(frame: pd.DataFrame, period: pd.Timestamp) -> pd.Series | None:
    candidates = frame.loc[frame["period_end"] == pd.Timestamp(period).normalize()].copy()
    if candidates.empty:
        return None
    candidates["manual_priority"] = candidates["source"].astype(str).str.contains(
        "manuell|manual", case=False, regex=True
    ).map({True: 0, False: 1})
    return candidates.sort_values(["manual_priority", "observed_date"]).iloc[0]


def _matching_trailing(series: pd.DataFrame, period: pd.Timestamp) -> pd.Series | None:
    matches = series.loc[series["as_of_date"] == pd.Timestamp(period).normalize()]
    if matches.empty:
        return None
    return matches.iloc[-1]


def _currency_and_value(trailing_row: pd.Series, components: list[pd.Series]) -> tuple[str, float] | None:
    trailing_currency = str(trailing_row["currency_code"] or "").strip().upper()
    component_currencies = {str(row["eps_currency"] or "").strip().upper() for row in components}
    component_currencies.discard("")
    if len(component_currencies) > 1:
        return None
    component_currency = next(iter(component_currencies), "")
    if trailing_currency and component_currency and trailing_currency != component_currency:
        return None
    currency = trailing_currency or component_currency
    if not currency:
        return None
    value = float(trailing_row["value"]) - sum(float(row["eps"]) for row in components)
    return (currency, value) if math.isfinite(value) else None


def _row(ticker: str, period: pd.Timestamp, eps: float, currency: str, observed: str, method: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "period_end": pd.Timestamp(period).normalize(),
        "report_date": pd.NaT,
        "observed_date": observed,
        "metric": DILUTED_METRIC,
        "eps": float(eps),
        "eps_currency": currency,
        "source": f"{SOURCE} / {method}",
    }


def _infer_next_quarter(period: pd.Timestamp) -> pd.Timestamp:
    period = pd.Timestamp(period).normalize()
    inferred = period + pd.DateOffset(months=3)
    if period.is_month_end:
        inferred = inferred + pd.offsets.MonthEnd(0)
    return pd.Timestamp(inferred).normalize()


def derive_missing_quarters() -> pd.DataFrame:
    if not AUDIT_FILE.exists() or AUDIT_FILE.stat().st_size == 0:
        raise FileNotFoundError(f"Saknar {AUDIT_FILE}")
    audit = pd.read_csv(AUDIT_FILE)
    required = {"ticker", "metric", "as_of_date", "value", "currency_code"}
    missing = sorted(required.difference(audit.columns))
    if missing:
        raise ValueError(f"Yahoo-audit saknar kolumner: {', '.join(missing)}")

    trailing = audit.loc[audit["metric"].astype(str) == "trailingDilutedEPS"].copy()
    trailing["as_of_date"] = pd.to_datetime(trailing["as_of_date"], errors="coerce").dt.normalize()
    trailing["value"] = pd.to_numeric(trailing["value"], errors="coerce")
    trailing["currency_code"] = trailing["currency_code"].fillna("").astype(str).str.strip().str.upper()
    trailing = trailing.dropna(subset=["ticker", "as_of_date", "value"])

    existing = load_quarterly_eps()
    working = _safe_diluted_rows(existing)
    observed = datetime.now(STOCKHOLM_TZ).date().isoformat()
    derived_rows: list[dict[str, object]] = []

    for ticker, ticker_trailing in trailing.groupby("ticker", sort=True):
        series = ticker_trailing.sort_values("as_of_date").drop_duplicates("as_of_date", keep="last").reset_index(drop=True)
        ticker_working = working.loc[working["ticker"].astype(str) == str(ticker)].copy()

        changed = True
        while changed:
            changed = False

            # A) Om Yahoo har TTM för en period som saknar diluted EPS, använd
            # de tre närmast föregående *sparade kvartalsperioderna*. Detta gör
            # att en period som nyss lösts av metod B kan användas direkt här.
            for trailing_row in series.itertuples(index=False):
                current = pd.Timestamp(trailing_row.as_of_date).normalize()
                if (ticker_working["period_end"] == current).any():
                    continue
                previous_periods = sorted(
                    set(ticker_working.loc[ticker_working["period_end"] < current, "period_end"].dropna().tolist())
                )[-3:]
                if len(previous_periods) != 3:
                    continue
                window = previous_periods + [current]
                gaps = [int((right - left).days) for left, right in zip(window, window[1:], strict=False)]
                span = int((current - previous_periods[0]).days)
                if max(gaps) > MAX_PERIOD_GAP_DAYS or not (MIN_WINDOW_SPAN_DAYS <= span <= MAX_WINDOW_SPAN_DAYS):
                    continue
                components = [_select_component(ticker_working, period) for period in previous_periods]
                if any(component is None for component in components):
                    continue
                trailing_series = pd.Series(trailing_row._asdict())
                resolved = _currency_and_value(trailing_series, [c for c in components if c is not None])
                if resolved is None:
                    continue
                currency, eps = resolved
                new_row = _row(str(ticker), current, eps, currency, observed, "same-period TTM")
                derived_rows.append(new_row)
                ticker_working = _safe_diluted_rows(pd.concat([ticker_working, pd.DataFrame([new_row])], ignore_index=True))
                changed = True
                break
            if changed:
                continue

            # B) Om Yahoo hoppar både kvartals- och TTM-raden i mitten av ett
            # Q2->Q4-gap: missing Q3 = TTM(Q4) - Q1 - Q2 - Q4.
            periods = sorted(set(ticker_working["period_end"].dropna().tolist()))
            for index in range(2, len(periods)):
                previous = pd.Timestamp(periods[index - 2]).normalize()
                left = pd.Timestamp(periods[index - 1]).normalize()
                right = pd.Timestamp(periods[index]).normalize()
                gap = int((right - left).days)
                if not (MIN_DOUBLE_QUARTER_GAP_DAYS <= gap <= MAX_DOUBLE_QUARTER_GAP_DAYS):
                    continue
                if int((left - previous).days) > MAX_SINGLE_QUARTER_GAP_DAYS:
                    continue
                inferred = _infer_next_quarter(left)
                if not (left < inferred < right):
                    continue
                if int((inferred - left).days) > MAX_SINGLE_QUARTER_GAP_DAYS or int((right - inferred).days) > MAX_SINGLE_QUARTER_GAP_DAYS:
                    continue
                trailing_right = _matching_trailing(series, right)
                if trailing_right is None:
                    continue
                components = [
                    _select_component(ticker_working, previous),
                    _select_component(ticker_working, left),
                    _select_component(ticker_working, right),
                ]
                if any(component is None for component in components):
                    continue
                resolved = _currency_and_value(trailing_right, [c for c in components if c is not None])
                if resolved is None:
                    continue
                currency, eps = resolved
                new_row = _row(str(ticker), inferred, eps, currency, observed, "next-period TTM bridge")
                derived_rows.append(new_row)
                ticker_working = _safe_diluted_rows(pd.concat([ticker_working, pd.DataFrame([new_row])], ignore_index=True))
                changed = True
                break

    if not derived_rows:
        print("Yahoo derived diluted EPS: inga nya perioder kunde eller behövde härledas.")
        return existing

    derived = pd.DataFrame(derived_rows, columns=QUARTERLY_COLUMNS)
    combined = pd.concat([existing, derived], ignore_index=True)
    save_quarterly_eps(combined)
    saved = load_quarterly_eps()
    _publish_json(saved)
    summary = {
        "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
        "derived_periods": len(derived),
        "derived_tickers": int(derived["ticker"].nunique()),
        "source": SOURCE,
        "methods": {
            "same_period": "quarter = trailingDilutedEPS(same period) - previous three quarterlyDilutedEPS",
            "next_period_bridge": "missing quarter = trailingDilutedEPS(next quarter) - other three quarters in that TTM window",
        },
    }
    (ROOT / "data" / "derived" / "quarterly_eps_derived_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Yahoo derived diluted EPS: härledde {len(derived)} saknade perioder för {derived['ticker'].nunique()} tickers.")
    return saved


def main() -> None:
    derive_missing_quarters()


if __name__ == "__main__":
    main()
