"""Persist report inputs and detect changes that invalidate published scores."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

from .config import ROOT

MANUAL_DATES = ROOT / "data/fundamentals/report_date_overrides.csv"
AUTO_DATES = ROOT / "data/fundamentals/report_date_rechecks.csv"
SCORE_DATES = ROOT / "data/derived/report_score_dates.csv"
DATE_COLUMNS = ["ticker", "report_period", "report_date", "source"]
SNAPSHOT_COLUMNS = ["ticker", "report_period", "effective_date", "period_end", "verified"]
EPS_COLUMNS = ["eps_ttm", "eps_currency", "valuation_date", "calculation_mode"]


def score_snapshot(reports: pd.DataFrame) -> pd.DataFrame:
    """Record the EPS and timing actually used by attach_eps_ttm, without FX."""
    from .fundamentals import (
        REPORT_CURRENCY_NOTE_PATTERN, TV_PERIOD_END_STATE,
        REPORT_DATE_STATE, TRADINGVIEW_SOURCE_PREFIX,
    )
    from .fx import load_stock_currencies
    result = reports[SNAPSHOT_COLUMNS + ["eps_ttm"]].copy()
    result["eps_currency"] = reports["notes"].astype("string").str.extract(
        REPORT_CURRENCY_NOTE_PATTERN, expand=False).str.upper()
    metadata = load_stock_currencies().drop_duplicates("ticker", keep="last")
    fallback = metadata.set_index("ticker")["report_currency"]
    result["eps_currency"] = result["eps_currency"].fillna(result.ticker.map(fallback)).fillna("")
    verified = reports.verified.astype(str).str.lower().isin(["true", "1"])
    usable = verified & reports.effective_date.notna() & reports.eps_ttm.notna()
    tv = set(reports.loc[usable & reports.source.astype(str).str.strip().str.startswith(TRADINGVIEW_SOURCE_PREFIX), "ticker"])
    result["calculation_mode"] = result.ticker.map(
        lambda ticker: TV_PERIOD_END_STATE if ticker in tv else REPORT_DATE_STATE)
    effective = pd.to_datetime(result.effective_date, errors="coerce")
    end = pd.to_datetime(result.period_end, errors="coerce")
    result["valuation_date"] = effective.where(
        ~result.calculation_mode.eq(TV_PERIOD_END_STATE) | end.isna() | end.gt(effective), end)
    return result


def changed_eps_cutoffs(reports: pd.DataFrame, previous: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Invalidate from the earliest old/new model date, only for changed inputs.

    Legacy date-only snapshots acquire EPS on their next successful build.
    They cannot prove an EPS change retrospectively.
    """
    if previous.empty or not set(EPS_COLUMNS).issubset(previous.columns):
        return {}
    current = score_snapshot(reports).set_index(["ticker", "report_period"])
    old = previous.set_index(["ticker", "report_period"])
    cutoffs = {}
    for key in old.index.union(current.index):
        before = old.loc[key] if key in old.index else None
        after = current.loc[key] if key in current.index else None
        def usable(row):
            return (row is not None and str(row.get("verified", False)).lower() in {"true", "1"}
                    and pd.notna(pd.to_datetime(row.get("effective_date"), errors="coerce"))
                    and pd.notna(pd.to_numeric(row.get("eps_ttm"), errors="coerce")))
        a, b = usable(before), usable(after)
        if not a and not b:
            continue
        same = (a and b and np.isclose(float(before.eps_ttm), float(after.eps_ttm), rtol=0, atol=1e-12)
                and str(before.eps_currency) == str(after.eps_currency)
                and str(before.calculation_mode) == str(after.calculation_mode)
                and pd.to_datetime(before.valuation_date) == pd.to_datetime(after.valuation_date))
        if same:
            continue
        days = [pd.Timestamp(row.valuation_date).normalize() for row, ok in ((before, a), (after, b)) if ok]
        day = min(days)
        ticker = str(key[0])
        cutoffs[ticker] = min(day, cutoffs.get(ticker, day))
    return cutoffs


def date_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=DATE_COLUMNS)
    frame = pd.read_csv(path, dtype=str).fillna("")
    if not set(DATE_COLUMNS).issubset(frame):
        raise ValueError(f"Rapportdatumfil saknar kolumner: {path}")
    if frame.duplicated(["ticker", "report_period"]).any():
        raise ValueError(f"Dubbla rapportdatum: {path}")
    return frame


def _date_mask(reports: pd.DataFrame, ticker: str, period: str, *, include_aliases: bool = False) -> pd.Series:
    exact = reports.ticker.eq(ticker) & reports.report_period.eq(period)
    if exact.any():
        if include_aliases:
            ends = reports.loc[exact, "period_end"].dropna()
            aliases = reports.ticker.eq(ticker) & reports.report_period.str.startswith("YAHOO-")
            exact = exact | (aliases & reports.period_end.isin(ends))
        return exact
    if "-Q" in period:
        quarter = pd.Period(period.replace("-Q", "Q"), freq="Q")
        candidates = reports.ticker.eq(ticker) & reports.period_end.dt.to_period("Q").eq(quarter)
        if int(candidates.sum()) == 1:
            return candidates
    return exact


def apply_date_evidence(reports: pd.DataFrame, *, manual_path: Path = MANUAL_DATES,
                        auto_path: Path = AUTO_DATES) -> pd.DataFrame:
    result = reports.copy()
    from .calendar_date_evidence import calendar_dates
    # EPS/Yahoo observations are fallback evidence; calendars then explicit
    # verified date corrections win independently of EPS value priority.
    for path, evidence in ((auto_path, date_overrides(auto_path)),
                           (None, calendar_dates(reports)),
                           (manual_path, date_overrides(manual_path))):
        for row in evidence.itertuples(index=False):
            mask = _date_mask(result, row.ticker, row.report_period,
                              include_aliases=path == manual_path)
            day = pd.to_datetime(row.report_date, errors="coerce")
            if pd.isna(day):
                raise ValueError(f"Ogiltigt rapportdatum: {row.ticker} {row.report_period}")
            result.loc[mask, "effective_date"] = pd.Timestamp(day).normalize()
            # A previous published_at must not keep driving marker/backtest dates.
            if "published_at" in result and mask.any():
                if path is None:
                    published = pd.to_datetime(result.loc[mask, 'published_at'], errors='coerce', utc=True)
                    local = published.dt.tz_convert('Europe/Stockholm').dt.tz_localize(None).dt.normalize()
                    # Retain actual publication time only when it agrees with calendar day.
                    result.loc[local.index[~local.eq(day)], 'published_at'] = pd.NaT
                elif path == auto_path and "published_at" in row._fields:
                    result.loc[mask, "published_at"] = pd.to_datetime(row.published_at, utc=True)
                else:
                    result.loc[mask, "published_at"] = pd.NaT
    return result


def verified_date_keys(reports: pd.DataFrame, path: Path = MANUAL_DATES, *,
                       include_calendar: bool = True) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in date_overrides(path).itertuples(index=False):
        mask = _date_mask(reports, row.ticker, row.report_period, include_aliases=True)
        keys.update((str(row.ticker), str(period)) for period in reports.loc[mask, "report_period"])
    if include_calendar:
        from .calendar_date_evidence import calendar_dates
        calendar = calendar_dates(reports)
        keys.update(zip(calendar.ticker, calendar.report_period))
    return keys


def changed_date_cutoffs(reports: pd.DataFrame, previous: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Rebase only a changed ticker, starting at the earlier old/new date."""
    if previous.empty:
        return {}
    old = previous.set_index(["ticker", "report_period"])
    current = reports.set_index(["ticker", "report_period"])
    cutoffs: dict[str, pd.Timestamp] = {}
    for key in old.index.union(current.index):
        before = old.loc[key] if key in old.index else None
        after = current.loc[key] if key in current.index else None
        def usable(row):
            if row is None or str(row.get("verified", False)).lower() not in {"true", "1"}:
                return pd.NaT
            return pd.to_datetime(row.get("effective_date"), errors="coerce")
        first, last = usable(before), usable(after)
        if (pd.isna(first) and pd.isna(last)) or (pd.notna(first) and pd.notna(last) and first == last):
            continue
        day = min(value for value in (first, last) if pd.notna(value)).normalize()
        ticker = str(key[0])
        cutoffs[ticker] = min(day, cutoffs.get(ticker, day))
    return cutoffs


def load_score_dates(path: Path = SCORE_DATES) -> pd.DataFrame:
    return pd.read_csv(path, float_precision="round_trip", keep_default_na=False) if path.exists() else pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def save_score_dates(reports: pd.DataFrame, path: Path = SCORE_DATES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    score_snapshot(reports).to_csv(temp, index=False)
    temp.replace(path)


def log_score_date_revisions(reports: pd.DataFrame, previous: pd.DataFrame,
                             generated_at: str, path: Path) -> None:
    if previous.empty:
        return
    snapshot = score_snapshot(reports)
    merged = previous.reindex(columns=snapshot.columns).merge(snapshot, on=["ticker", "report_period"],
                            how="outer", suffixes=("_old", "_new"))
    old = pd.to_datetime(merged.effective_date_old, errors="coerce")
    new = pd.to_datetime(merged.effective_date_new, errors="coerce")
    changed = ~(old.eq(new) | (old.isna() & new.isna()))
    if set(EPS_COLUMNS).issubset(previous.columns):
        same_eps = np.isclose(pd.to_numeric(merged.eps_ttm_old, errors="coerce"),
                              pd.to_numeric(merged.eps_ttm_new, errors="coerce"),
                              rtol=0, atol=1e-12, equal_nan=True)
        changed |= ~same_eps | merged.eps_currency_old.fillna("").ne(merged.eps_currency_new.fillna(""))
        changed |= merged.calculation_mode_old.fillna("").ne(merged.calculation_mode_new.fillna(""))
    columns = ["ticker", "report_period", "effective_date_old", "effective_date_new",
               "eps_ttm_old", "eps_ttm_new", "eps_currency_old", "eps_currency_new",
               "valuation_date_old", "valuation_date_new"]
    rows = merged.loc[changed, columns].copy()
    if rows.empty:
        return
    rows["rebuilt_at"] = generated_at
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame()
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([existing, rows], ignore_index=True).to_csv(path, index=False)
