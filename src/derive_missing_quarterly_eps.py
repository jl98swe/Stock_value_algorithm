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

    trailing_value = float(trailing_row["value"])
    derived_eps = trailing_value - sum(float(row["eps"]) for row in components)
    if not math.isfinite(derived_eps):
        return None
    return currency, float(derived_eps)


def _derived_row(
    *,
    ticker: str,
    period_end: pd.Timestamp,
    eps: float,
    currency: str,
    observed_date: str,
    method: str,
) -> dict[str, object]:
    return {
        "ticker": str(ticker),
        "period_end": pd.Timestamp(period_end).normalize(),
        "report_date": pd.NaT,
        "observed_date": observed_date,
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

        # Metod 1: Yahoo har TTM för den saknade perioden. Då är periodens
        # diluted EPS exakt TTM minus de tre föregående periodkomponenterna.
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

            components = [_select_component(ticker_working, period) for period in previous_periods]
            if any(component is None for component in components):
                continue
            resolved = _currency_and_value(current, [component for component in components if component is not None])
            if resolved is None:
                continue
            currency, derived_eps = resolved
            row = _derived_row(
                ticker=str(ticker),
                period_end=current_period,
                eps=derived_eps,
                currency=currency,
                observed_date=observed_date,
                method="same-period TTM",
            )
            derived_rows.append(row)
            ticker_working = _safe_diluted_rows(
                pd.concat([ticker_working, pd.DataFrame([row], columns=QUARTERLY_COLUMNS)], ignore_index=True)
            )

        # Metod 2: Yahoo hoppar både kvartalsraden och TTM-raden för ett kvartal
        # (detta sker systematiskt för många Q3 2025-rader). Om det finns ett
        # tvåkvartalsgap Q2 -> Q4 kan Q3 lösas exakt från TTM vid Q4:
        # Q3 = TTM(Q4) - Q1 - Q2 - Q4.
        changed = True
        while changed:
            changed = False
            periods = sorted(set(ticker_working["period_end"].dropna().tolist()))
            for index in range(1, len(periods)):
                left = pd.Timestamp(periods[index - 1]).normalize()
                right = pd.Timestamp(periods[index]).normalize()
                gap_days = int((right - left).days)
                if gap_days < MIN_DOUBLE_QUARTER_GAP_DAYS or gap_days > MAX_DOUBLE_QUARTER_GAP_DAYS:
                    continue
                if index < 2:
                    continue

                previous = pd.Timestamp(periods[index - 2]).normalize()
                if int((left - previous).days) > MAX_SINGLE_QUARTER_GAP_DAYS:
                    continue

                inferred = _infer_next_quarter(left)
                if not (left < inferred < right):
                    continue
                if int((inferred - left).days) > MAX_SINGLE_QUARTER_GAP_DAYS:
                    continue
                if int((right - inferred).days) > MAX_SINGLE_QUARTER_GAP_DAYS:
                    continue
                if (ticker_working["period_end"] == inferred).any():
                    continue

                trailing_right = _matching_trailing(series, right)
                if trailing_right is None:
                    continue
                component_rows = [
                    _select_component(ticker_working, previous),
                    _select_component(ticker_working, left),
                    _select_component(ticker_working, right),
                ]
                if any(component is None for component in component_rows):
                    continue
                resolved = _currency_and_value(
                    trailing_right,
                    [component for component in component_rows if component is not None],
                )
                if resolved is None:
                    continue
                currency, derived_eps = resolved
                row = _derived_row(
                    ticker=str(ticker),
                    period_end=inferred,
                    eps=derived_eps,
                    currency=currency,
                    observed_date=observed_date,
                    method="next-period TTM bridge",
                )
                derived_rows.append(row)
                ticker_working = _safe_diluted_rows(
                    pd.concat([ticker_working, pd.DataFrame([row], columns=QUARTERLY_COLUMNS)], ignore_index=True)
                )
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

    audit_output = {
        "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
        "derived_periods": len(derived),
        "derived_tickers": int(derived["ticker"].nunique()),
        "source": SOURCE,
        "methods": {
            "same_period": "quarter = trailingDilutedEPS(same period) - previous three quarterlyDilutedEPS",
            "next_period_bridge": "missing quarter = trailingDilutedEPS(next quarter) - other three quarters in that TTM window",
        },
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
