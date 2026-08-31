from __future__ import annotations

import math

import pandas as pd

from .earnings import EPS_SOURCE, load_earnings_history
from .quarterly_eps import DILUTED_METRIC, MANUAL_METRIC, load_quarterly_eps

DERIVED_MANUAL_MARKER = "manual_quarterly_eps_derived_v1"
SAFE_METRICS = {MANUAL_METRIC, DILUTED_METRIC}
METRIC_PRIORITY = {MANUAL_METRIC: 0, DILUTED_METRIC: 1}
MAX_PRIOR_YEAR_DISTANCE_DAYS = 21
MAX_PREVIOUS_PERIOD_GAP_DAYS = 170


def _target_prior_year(period_end: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(period_end).normalize()
    target = timestamp - pd.DateOffset(years=1)
    if timestamp.is_month_end:
        target = target + pd.offsets.MonthEnd(0)
    return pd.Timestamp(target).normalize()


def find_prior_year_diluted_eps(
    ticker: str,
    period_end: object,
    frame: pd.DataFrame | None = None,
) -> pd.Series | None:
    data = load_quarterly_eps() if frame is None else frame.copy()
    if data.empty:
        return None

    for column in ("ticker", "period_end", "observed_date", "metric", "eps", "eps_currency"):
        if column not in data.columns:
            data[column] = pd.NA
    data["ticker"] = data["ticker"].astype(str).str.strip()
    data["period_end"] = pd.to_datetime(data["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["observed_date"] = pd.to_datetime(data["observed_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["eps"] = pd.to_numeric(data["eps"], errors="coerce")
    data["eps_currency"] = data["eps_currency"].fillna("").astype(str).str.strip().str.upper()

    target = _target_prior_year(pd.Timestamp(period_end))
    subset = data.loc[
        (data["ticker"] == str(ticker).strip())
        & data["metric"].isin(SAFE_METRICS)
        & data["period_end"].notna()
        & data["eps"].notna()
    ].copy()
    if subset.empty:
        return None

    subset["distance_days"] = (subset["period_end"] - target).abs().dt.days
    subset = subset.loc[subset["distance_days"] <= MAX_PRIOR_YEAR_DISTANCE_DAYS].copy()
    if subset.empty:
        return None
    subset["metric_priority"] = subset["metric"].map(METRIC_PRIORITY).fillna(99)
    return subset.sort_values(["distance_days", "metric_priority", "observed_date"]).iloc[0]


def _normalise_earnings(frame: pd.DataFrame | None) -> pd.DataFrame:
    result = load_earnings_history() if frame is None else frame.copy()
    for column in ["ticker", "period_end", "observed_date", "eps_ttm", "eps_currency", "source"]:
        if column not in result.columns:
            result[column] = pd.NA
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["period_end"] = pd.to_datetime(result["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["observed_date"] = pd.to_datetime(result["observed_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["eps_currency"] = result["eps_currency"].fillna("").astype(str).str.strip().str.upper()
    result["source"] = result["source"].fillna("").astype(str).str.strip()
    return result


def derive_manual_eps_ttm_safe(
    *,
    ticker: str,
    period_end: object,
    current_period_eps: float,
    quarterly_frame: pd.DataFrame | None = None,
    earnings_frame: pd.DataFrame | None = None,
) -> dict[str, object]:
    period = pd.to_datetime(period_end, errors="coerce")
    if pd.isna(period):
        raise ValueError("period_end är inte ett giltigt datum")
    period = pd.Timestamp(period).tz_localize(None).normalize()
    current_eps = float(current_period_eps)
    if not math.isfinite(current_eps):
        raise ValueError("EPS måste vara ett ändligt tal")

    prior = find_prior_year_diluted_eps(ticker, period, quarterly_frame)
    if prior is None:
        target = _target_prior_year(period).date().isoformat()
        raise ValueError(
            f"Saknar sparad utspädd EPS för {ticker} omkring motsvarande rapportperiod {target}. "
            "Yahoo Reported EPS används inte som ersättning eftersom måttdefinitionen kan skilja sig."
        )

    earnings = _normalise_earnings(earnings_frame)
    subset = earnings.loc[
        (earnings["ticker"] == str(ticker).strip())
        & (earnings["source"] == EPS_SOURCE)
        & earnings["period_end"].notna()
        & (earnings["period_end"] < period)
        & earnings["eps_ttm"].notna()
        & earnings["eps_currency"].str.len().gt(0)
    ].copy()
    if subset.empty:
        raise ValueError(
            f"Saknar föregående Yahoo trailingDilutedEPS för {ticker}; kan inte härleda ny TTM säkert."
        )

    previous = subset.sort_values(["period_end", "observed_date"]).iloc[-1]
    gap_days = int((period - pd.Timestamp(previous["period_end"]).normalize()).days)
    if gap_days <= 0 or gap_days > MAX_PREVIOUS_PERIOD_GAP_DAYS:
        raise ValueError(
            f"Föregående Yahoo TTM-period för {ticker} ligger {gap_days} dagar från nya perioden; "
            "automatisk härledning stoppas."
        )

    previous_currency = str(previous["eps_currency"] or "").strip().upper()
    prior_currency = str(prior["eps_currency"] or "").strip().upper()
    if prior_currency and previous_currency and prior_currency != previous_currency:
        raise ValueError(
            f"Valutakonflikt för {ticker}: föregående TTM är {previous_currency}, "
            f"föregående års utspädda period-EPS är {prior_currency}."
        )
    currency = previous_currency or prior_currency
    if not currency:
        raise ValueError(f"Saknar EPS-valuta för {ticker}; TTM härleds inte.")

    previous_ttm = float(previous["eps_ttm"])
    prior_eps = float(prior["eps"])
    derived_ttm = previous_ttm + current_eps - prior_eps
    if not math.isfinite(derived_ttm):
        raise ValueError("Härledd EPS TTM blev inte ett ändligt tal")

    audit_note = (
        f"{DERIVED_MANUAL_MARKER}; previous_ttm={previous_ttm:.12g}; "
        f"previous_period_end={pd.Timestamp(previous['period_end']).date().isoformat()}; "
        f"current_period_eps={current_eps:.12g}; prior_year_eps={prior_eps:.12g}; "
        f"prior_year_period_end={pd.Timestamp(prior['period_end']).date().isoformat()}; "
        f"prior_year_metric={prior['metric']}; report_currency={currency}"
    )
    return {
        "eps_ttm": float(derived_ttm),
        "eps_currency": currency,
        "previous_ttm": previous_ttm,
        "previous_period_end": pd.Timestamp(previous["period_end"]).normalize(),
        "prior_year_eps": prior_eps,
        "prior_year_period_end": pd.Timestamp(prior["period_end"]).normalize(),
        "prior_year_metric": str(prior["metric"]),
        "audit_note": audit_note,
    }
