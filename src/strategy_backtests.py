"""Independent strategy variants; the existing Standard state machine stays shared."""
from __future__ import annotations

from functools import lru_cache
from typing import Callable

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .reporting import _combined_schedule, load_auto_report_calendar, CALENDAR_HISTORY_FILE
from .config import ROOT
from .strategy import run_strategy


@lru_cache(maxsize=1)
def automatic_calendar() -> pd.DataFrame:
    return load_auto_report_calendar()


def report_filters(frame: pd.DataFrame, report_dates: list[pd.Timestamp],
                   known_from: dict[pd.Timestamp, pd.Timestamp] | None = None) -> pd.DataFrame:
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
    knowledge = known_from or {}
    known = pd.DatetimeIndex([knowledge.get(day, pd.Timestamp('1900-01-01')) for day in reports])
    # Calendar information must already be known on the signal day. A later
    # observation must not unlock an earlier historical purchase.
    available = (reports.values[None, :] >= dates.values[:, None]) & (known.values[None, :] <= dates.values[:, None])
    valid = available.any(axis=1)
    next_dates = reports[available.argmax(axis=1)]
    distances = sessions.searchsorted(next_dates, side="right") - sessions.searchsorted(dates, side="right")
    allowed = valid & (distances > 10) & (next_dates > dates)
    data["BuyExecutionAllowed"] = allowed
    # Both the signal day and the actual next opening must be outside the block.
    next_sessions = sessions[sessions.searchsorted(dates, side="right")]
    next_available = (reports.values[None, :] >= next_sessions.values[:, None]) & (known.values[None, :] <= dates.values[:, None])
    next_valid = next_available.any(axis=1)
    next_reports = reports[next_available.argmax(axis=1)]
    next_distances = sessions.searchsorted(next_reports, side="right") - sessions.searchsorted(next_sessions, side="right")
    data["BuyAllowed"] = allowed & next_valid & (next_reports > next_sessions) & (next_distances > 10)
    exits = {sessions[sessions.searchsorted(day, side="left") - 1] for day in reports
             if sessions.searchsorted(day, side="left") > 0
             and knowledge.get(day, pd.Timestamp('1900-01-01')) <= sessions[sessions.searchsorted(day, side="left") - 1]}
    data["ForceReportExit"] = dates.isin(exits)
    return data



@lru_cache(maxsize=1)
def calendar_history() -> pd.DataFrame:
    return load_auto_report_calendar(CALENDAR_HISTORY_FILE)


@lru_cache(maxsize=1)
def legacy_calendar_knowledge() -> pd.DataFrame:
    path = ROOT / 'data/manual/report_calendar_knowledge_overrides.csv'
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=['ticker', 'report_date', 'known_from'])


def report_knowledge(ticker: str, dates: list[pd.Timestamp]) -> dict[pd.Timestamp, pd.Timestamp]:
    """Preserve legacy simulations; freeze observation timing for new cycles.

    Announcements from the next report cycle (5 Nov 2026 onward) use their first
    archived observation, also after that report becomes a realised report.
    The migration manifest preserves previously published simulations unless
    an audited correction supplies an actual observation date. It does not
    pretend that legacy announcement timestamps are known.
    """
    frames = [f for f in (calendar_history(), automatic_calendar()) if not f.empty]
    evidence = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not evidence.empty:
        evidence = evidence.loc[evidence.ticker.astype(str).eq(ticker)].copy()
        evidence['report_date_start'] = pd.to_datetime(evidence.report_date_start)
        evidence['observed_date'] = pd.to_datetime(evidence.observed_date)
    knowledge = {}
    for day in sorted(set(dates)):
        if day < pd.Timestamp('2026-11-05'):
            continue
        matching = evidence.loc[evidence.report_date_start.eq(day), 'observed_date'] if not evidence.empty else pd.Series(dtype='datetime64[ns]')
        # Missing knowledge cannot grant a historical buy. Fallback is the
        # release day; no observation date is invented.
        knowledge[day] = matching.min() if matching.notna().any() else day
    overrides = legacy_calendar_knowledge()
    for row in overrides.loc[overrides.ticker.eq(ticker)].itertuples(index=False):
        day = pd.Timestamp(row.report_date)
        if str(getattr(row, 'legacy_preserve', False)).lower() == 'true':
            knowledge.pop(day, None)
        else:
            knowledge[day] = pd.Timestamp(row.known_from)
    return knowledge


def build_strategy_backtests(frame: pd.DataFrame, ticker: str, reports: pd.DataFrame,
                            manual_calendar: pd.DataFrame, standard: dict,
                            live_payload_builder: Callable | None = None) -> dict:
    historical = reports.loc[reports["ticker"].astype(str) == ticker]
    dates = []
    for row in historical.itertuples(index=False):
        published = pd.to_datetime(getattr(row, "published_at", None), errors="coerce", utc=True)
        day = (published.tz_convert("Europe/Stockholm").tz_localize(None).normalize()
               if pd.notna(published) else pd.to_datetime(getattr(row, "effective_date", None), errors="coerce"))
        official = pd.to_datetime(getattr(row, "report_date", None), errors="coerce")
        if pd.notna(official):
            day = official
        if pd.notna(day):
            dates.append(pd.Timestamp(day).normalize())
    schedule = _combined_schedule(automatic_calendar(), manual_calendar)
    if not schedule.empty:
        future = schedule.loc[schedule["ticker"].astype(str) == ticker, "report_date_start"]
        # Prefer realised dates for past reports; schedules supply only future dates.
        # An opening observation must not age today's scheduled report out of
        # the historical simulation (and thereby erase yesterday's report exit).
        completed = frame.loc[~frame.get("OpeningOnly", pd.Series(False, index=frame.index)).fillna(False).astype(bool)]
        completed_day = completed["Date"].max()
        dates.extend(pd.Timestamp(d).normalize() for d in future if pd.notna(d) and d > completed_day)
    ma = frame.copy()
    ma["BuyAllowed"] = (ma["Close"] > ma["MA200"]) & ma["MA200"].notna()
    # At the next open only the previous close's completed MA200 is known.
    ma["BuyExecutionAllowed"] = ma["BuyAllowed"].shift(1, fill_value=False) & (ma["Open"] > ma["MA200"].shift(1))
    knowledge = report_knowledge(ticker, dates)
    report_frame = report_filters(frame, dates, knowledge)
    variants = {"standard": standard, "ma200": run_strategy(ma, ticker),
                "report_avoidance": run_strategy(report_frame, ticker),
                "standard_stop_loss_10": run_strategy(frame, ticker, stop_loss_pct=10),
                "standard_two_positions": run_strategy(frame, ticker, max_lots=2,
                    buy_rearm_score=5, sell_rearm_score=95)}
    names = {"standard": "Standard", "ma200": "MA200", "report_avoidance": "Rapportundvikande",
             "standard_stop_loss_10": "Standard — stop loss 10 %",
             "standard_two_positions": "Standard — två positioner"}
    result = {}
    latest_day = pd.Timestamp(frame["Date"].max()).normalize()
    sessions = xcals.get_calendar("XSTO", start=latest_day - pd.Timedelta(days=15),
                                  end=max([latest_day + pd.Timedelta(days=30), *dates])).sessions
    sessions = sessions.tz_localize(None) if sessions.tz is not None else sessions
    next_session = sessions[sessions.searchsorted(latest_day, side="right")]
    next_report = min((day for day in dates if day >= latest_day and knowledge.get(day, pd.Timestamp("1900-01-01")) <= latest_day), default=None)
    report_exit = sessions[sessions.searchsorted(next_report, side="left") - 1] if next_report is not None else None
    filter_info = {
        "standard": {"buy_allowed": True, "buy_block_reason": ""},
        "standard_two_positions": {"buy_allowed": True, "buy_block_reason": "", "max_lots": 2},
        "standard_stop_loss_10": {"buy_allowed": True, "buy_block_reason": "", "stop_loss_pct": 10,
            "stop_price": next((lot["entry_price"] * .9 for lot in variants["standard_stop_loss_10"].get("open_lots", [])), None)},
        "ma200": {"buy_allowed": bool(ma.iloc[-1]["BuyAllowed"]),
                  "buy_block_reason": "Köp kräver kurs över MA200"},
        "report_avoidance": {"buy_allowed": bool(report_frame.iloc[-1]["BuyAllowed"]),
                             "basis_date": latest_day.date().isoformat(),
                             "buy_block_reason": "Köp blockerat inför rapport" if next_report is not None else "Nästa rapportdatum saknas",
                             "next_report_date": next_report.date().isoformat() if next_report is not None else None,
                             "trading_days_to_report": int(sessions.searchsorted(next_report, side="right") - sessions.searchsorted(latest_day, side="right")) if next_report is not None else None,
                             "report_exit_date": report_exit.date().isoformat() if report_exit is not None and report_exit > latest_day else None,
                             "force_next_exit": report_exit == next_session if report_exit is not None else False},
    }
    for key in ("standard", "standard_stop_loss_10", "standard_two_positions", "ma200", "report_avoidance"):
        variant = variants[key]
        result[key] = {"name": names[key], "closed_trades": variant.get("trades", []),
                       "max_lots": variant.get("summary", {}).get("max_lots", 1),
                       "open_lots": variant.get("open_lots", []),
                       "start_date": frame["Date"].min().date().isoformat(),
                       "end_date": frame["Date"].max().date().isoformat()}
        if live_payload_builder is not None:
            result[key]["overview"] = live_payload_builder(variant, filter_info[key])
    result["report_avoidance"]["report_date_basis"] = "archived_calendar_observations_for_new_cycles"
    result["report_avoidance"]["report_dates_count"] = len(set(dates))
    result["report_avoidance"]["missing_next_report_days"] = int((~report_frame["BuyExecutionAllowed"] & ~report_frame["ForceReportExit"]).sum()) if not dates else int((frame["Date"] > max(dates)).sum())
    return result
