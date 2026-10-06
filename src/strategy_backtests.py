"""Independent strategy variants; the existing Standard state machine stays shared."""
from __future__ import annotations

from functools import lru_cache
from typing import Callable

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .reporting import _combined_schedule, load_auto_report_calendar
from .strategy import run_strategy


@lru_cache(maxsize=1)
def automatic_calendar() -> pd.DataFrame:
    return load_auto_report_calendar()


def report_filters(frame: pd.DataFrame, report_dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Count exchange sessions, never weekdays or available price rows."""
    data = frame.copy()
    dates = pd.DatetimeIndex(pd.to_datetime(data["Date"]).dt.normalize())
    report_dates = sorted(set(pd.Timestamp(d).normalize() for d in report_dates if pd.notna(d)))
    data["BuyAllowed"] = False
    data["BuyExecutionAllowed"] = False
    data["ForceReportExit"] = False
    if not len(dates) or not report_dates:
        return data
    sessions = xcals.get_calendar("XSTO", start=dates.min() - pd.Timedelta(days=15),
                                  end=max(dates.max(), max(report_dates)) + pd.Timedelta(days=15)).sessions
    sessions = sessions.tz_localize(None) if sessions.tz is not None else sessions
    reports = pd.DatetimeIndex(report_dates)
    next_indices = reports.searchsorted(dates, side="left")
    valid = next_indices < len(reports)
    next_dates = reports[np.minimum(next_indices, len(reports) - 1)]
    distances = sessions.searchsorted(next_dates, side="right") - sessions.searchsorted(dates, side="right")
    allowed = valid & (distances > 10) & (next_dates > dates)
    data["BuyExecutionAllowed"] = allowed
    # Both the signal day and the actual next opening must be outside the block.
    next_sessions = sessions[sessions.searchsorted(dates, side="right")]
    next_report_indices = reports.searchsorted(next_sessions, side="left")
    next_valid = next_report_indices < len(reports)
    next_reports = reports[np.minimum(next_report_indices, len(reports) - 1)]
    next_distances = sessions.searchsorted(next_reports, side="right") - sessions.searchsorted(next_sessions, side="right")
    data["BuyAllowed"] = allowed & next_valid & (next_reports > next_sessions) & (next_distances > 10)
    exits = {sessions[sessions.searchsorted(day, side="left") - 1] for day in reports
             if sessions.searchsorted(day, side="left") > 0}
    data["ForceReportExit"] = dates.isin(exits)
    return data


def build_strategy_backtests(frame: pd.DataFrame, ticker: str, reports: pd.DataFrame,
                            manual_calendar: pd.DataFrame, standard: dict,
                            live_payload_builder: Callable | None = None) -> dict:
    historical = reports.loc[reports["ticker"].astype(str) == ticker]
    dates = []
    for row in historical.itertuples(index=False):
        published = pd.to_datetime(getattr(row, "published_at", None), errors="coerce", utc=True)
        day = (published.tz_convert("Europe/Stockholm").tz_localize(None).normalize()
               if pd.notna(published) else pd.to_datetime(getattr(row, "effective_date", None), errors="coerce"))
        if pd.notna(day):
            dates.append(pd.Timestamp(day).normalize())
    schedule = _combined_schedule(automatic_calendar(), manual_calendar)
    if not schedule.empty:
        future = schedule.loc[schedule["ticker"].astype(str) == ticker, "report_date_start"]
        # Prefer realised dates for past reports; schedules supply only future dates.
        dates.extend(pd.Timestamp(d).normalize() for d in future if pd.notna(d) and d > frame["Date"].max())
    ma = frame.copy()
    ma["BuyAllowed"] = (ma["Close"] > ma["MA200"]) & ma["MA200"].notna()
    # At the next open only the previous close's completed MA200 is known.
    ma["BuyExecutionAllowed"] = ma["BuyAllowed"].shift(1, fill_value=False) & (ma["Open"] > ma["MA200"].shift(1))
    report_frame = report_filters(frame, dates)
    variants = {"standard": standard, "ma200": run_strategy(ma, ticker),
                "report_avoidance": run_strategy(report_frame, ticker)}
    names = {"standard": "Standard", "ma200": "MA200", "report_avoidance": "Rapportundvikande"}
    result = {}
    latest_day = pd.Timestamp(frame["Date"].max()).normalize()
    sessions = xcals.get_calendar("XSTO", start=latest_day - pd.Timedelta(days=15),
                                  end=max([latest_day + pd.Timedelta(days=30), *dates])).sessions
    sessions = sessions.tz_localize(None) if sessions.tz is not None else sessions
    next_session = sessions[sessions.searchsorted(latest_day, side="right")]
    next_report = min((day for day in dates if day >= latest_day), default=None)
    report_exit = sessions[sessions.searchsorted(next_report, side="left") - 1] if next_report is not None else None
    filter_info = {
        "standard": {"buy_allowed": True, "buy_block_reason": ""},
        "ma200": {"buy_allowed": bool(ma.iloc[-1]["BuyAllowed"]),
                  "buy_block_reason": "Köp kräver kurs över MA200"},
        "report_avoidance": {"buy_allowed": bool(report_frame.iloc[-1]["BuyAllowed"]),
                             "buy_block_reason": "Köp blockerat inför rapport" if next_report is not None else "Nästa rapportdatum saknas",
                             "next_report_date": next_report.date().isoformat() if next_report is not None else None,
                             "report_exit_date": report_exit.date().isoformat() if report_exit is not None and report_exit > latest_day else None,
                             "force_next_exit": report_exit == next_session if report_exit is not None else False},
    }
    for key, variant in variants.items():
        result[key] = {"name": names[key], "closed_trades": variant.get("trades", []),
                       "open_lots": variant.get("open_lots", []),
                       "start_date": frame["Date"].min().date().isoformat(),
                       "end_date": frame["Date"].max().date().isoformat()}
        if live_payload_builder is not None:
            result[key]["overview"] = live_payload_builder(variant, filter_info[key])
    result["report_avoidance"]["report_date_basis"] = "final_report_dates"
    result["report_avoidance"]["report_dates_count"] = len(set(dates))
    result["report_avoidance"]["missing_next_report_days"] = int((~report_frame["BuyExecutionAllowed"] & ~report_frame["ForceReportExit"]).sum()) if not dates else int((frame["Date"] > max(dates)).sum())
    return result
