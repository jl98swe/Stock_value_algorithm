"""Select only companies whose newly reported EPS data is still missing."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .earnings import load_earnings_history
from .quarterly_eps import DILUTED_METRIC, MANUAL_METRIC, load_quarterly_eps
from .reporting import CALENDAR_HISTORY_FILE, load_auto_report_calendar

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
POLL_WINDOW_DAYS = 45


def _recent_report_dates(today: object | None = None) -> pd.DataFrame:
    day = (
        pd.Timestamp(today).tz_localize(None).normalize()
        if today is not None
        else pd.Timestamp(datetime.now(STOCKHOLM_TZ).date())
    )
    current = load_auto_report_calendar()
    history = load_auto_report_calendar(CALENDAR_HISTORY_FILE)
    calendar = pd.concat([current, history], ignore_index=True)
    if calendar.empty:
        return pd.DataFrame(columns=["ticker", "report_date"])
    calendar = calendar.copy()
    calendar["report_date_start"] = pd.to_datetime(
        calendar["report_date_start"], errors="coerce"
    ).dt.tz_localize(None).dt.normalize()
    calendar["observed_date"] = pd.to_datetime(
        calendar["observed_date"], errors="coerce"
    ).dt.tz_localize(None).dt.normalize()
    calendar = calendar.loc[
        calendar["report_date_start"].between(day - pd.Timedelta(days=POLL_WINDOW_DAYS), day)
    ].copy()
    if calendar.empty:
        return pd.DataFrame(columns=["ticker", "report_date"])
    calendar = calendar.sort_values(["ticker", "report_date_start", "observed_date"])
    calendar = calendar.drop_duplicates("ticker", keep="last")
    return calendar[["ticker", "report_date_start"]].rename(columns={"report_date_start": "report_date"})


def _pending(events: pd.DataFrame, values: pd.DataFrame) -> list[str]:
    pending: list[str] = []
    for event in events.itertuples(index=False):
        ticker = str(event.ticker)
        report_date = pd.Timestamp(event.report_date).normalize()
        rows = values.loc[values["ticker"].astype(str) == ticker].copy()
        if rows.empty:
            pending.append(ticker)
            continue
        rows["period_end"] = pd.to_datetime(rows["period_end"], errors="coerce").dt.normalize()
        rows["observed_date"] = pd.to_datetime(rows["observed_date"], errors="coerce").dt.normalize()
        baseline = rows.loc[rows["observed_date"] < report_date, "period_end"].dropna()
        if baseline.empty:
            pending.append(ticker)
            continue
        if not bool((rows["period_end"] > baseline.max()).any()):
            pending.append(ticker)
    return sorted(set(pending))


def pending_ttm_tickers(today: object | None = None) -> list[str]:
    return _pending(_recent_report_dates(today), load_earnings_history())


def pending_quarterly_tickers(today: object | None = None) -> list[str]:
    quarterly = load_quarterly_eps()
    if not quarterly.empty:
        quarterly = quarterly.loc[quarterly["metric"].isin({DILUTED_METRIC, MANUAL_METRIC})]
    return _pending(_recent_report_dates(today), quarterly)
