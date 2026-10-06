"""Persist date evidence separately from EPS and detect changed scoring dates."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT

MANUAL_DATES = ROOT / "data/fundamentals/report_date_overrides.csv"
AUTO_DATES = ROOT / "data/fundamentals/report_date_rechecks.csv"
SCORE_DATES = ROOT / "data/derived/report_score_dates.csv"
DATE_COLUMNS = ["ticker", "report_period", "report_date", "source"]
SNAPSHOT_COLUMNS = ["ticker", "report_period", "effective_date", "period_end", "verified"]


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
    # Manual date evidence wins, independently of who supplied the EPS value.
    for path in (auto_path, manual_path):
        for row in date_overrides(path).itertuples(index=False):
            mask = _date_mask(result, row.ticker, row.report_period,
                              include_aliases=path == manual_path)
            day = pd.to_datetime(row.report_date, errors="coerce")
            if pd.isna(day):
                raise ValueError(f"Ogiltigt rapportdatum: {row.ticker} {row.report_period}")
            result.loc[mask, "effective_date"] = pd.Timestamp(day).normalize()
            # A previous published_at must not keep driving marker/backtest dates.
            if "published_at" in result and mask.any():
                if path == auto_path and "published_at" in row._fields:
                    result.loc[mask, "published_at"] = pd.to_datetime(row.published_at, utc=True)
                else:
                    result.loc[mask, "published_at"] = pd.NaT
    return result


def verified_date_keys(reports: pd.DataFrame, path: Path = MANUAL_DATES) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in date_overrides(path).itertuples(index=False):
        mask = _date_mask(reports, row.ticker, row.report_period, include_aliases=True)
        keys.update((str(row.ticker), str(period)) for period in reports.loc[mask, "report_period"])
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
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def save_score_dates(reports: pd.DataFrame, path: Path = SCORE_DATES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    reports[SNAPSHOT_COLUMNS].to_csv(temp, index=False)
    temp.replace(path)


def log_score_date_revisions(reports: pd.DataFrame, previous: pd.DataFrame,
                             generated_at: str, path: Path) -> None:
    if previous.empty:
        return
    merged = previous.merge(reports[SNAPSHOT_COLUMNS], on=["ticker", "report_period"],
                            how="outer", suffixes=("_old", "_new"))
    old = pd.to_datetime(merged.effective_date_old, errors="coerce")
    new = pd.to_datetime(merged.effective_date_new, errors="coerce")
    changed = ~(old.eq(new) | (old.isna() & new.isna()))
    rows = merged.loc[changed, ["ticker", "report_period", "effective_date_old", "effective_date_new"]].copy()
    if rows.empty:
        return
    rows["rebuilt_at"] = generated_at
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame()
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([existing, rows], ignore_index=True).to_csv(path, index=False)
