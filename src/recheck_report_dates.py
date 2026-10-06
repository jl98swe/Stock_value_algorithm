"""Check report-date evidence after 7 and 14 days, independently of EPS changes."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yfinance as yf

from .config import ROOT
from .fundamentals import load_reports, save_reports
from .report_date_revisions import AUTO_DATES, MANUAL_DATES, date_overrides, verified_date_keys
from .utils import read_json, write_json_atomic

STATE_FILE = ROOT / "data/earnings/report_date_check_state.json"
AUDIT_FILE = ROOT / "data/derived/report_date_checks.csv"
STATUS_FILE = ROOT / "data/earnings/report_date_status.json"
MILESTONES = (0, 7, 14)
WINDOW_DAYS = 45
TZ = ZoneInfo("Europe/Stockholm")


def effective_date(timestamp: object) -> pd.Timestamp:
    """Use the exchange's real close, including half-days and daylight saving."""
    value = pd.Timestamp(timestamp)
    local = value.tz_localize(TZ) if value.tzinfo is None else value.tz_convert(TZ)
    day = pd.Timestamp(local.date())
    calendar = xcals.get_calendar("XSTO")
    session = calendar.date_to_session(day, direction="next")
    if calendar.is_session(day) and local.tz_convert("UTC") >= calendar.session_close(session):
        session = calendar.next_session(session)
    return pd.Timestamp(session).tz_localize(None).normalize()


def select_report_timestamp(dates: pd.DataFrame, anchor: object, today: object) -> pd.Timestamp | None:
    """Match the same release, never an unrelated old/future earnings event."""
    if dates is None or dates.empty or "Reported EPS" not in dates:
        return None
    anchor = pd.Timestamp(anchor).normalize()
    last_day = pd.Timestamp(today).normalize()
    candidates = []
    for timestamp, row in dates.iterrows():
        if pd.isna(row.get("Reported EPS")):
            continue
        value = pd.Timestamp(timestamp)
        local = value.tz_localize(TZ) if value.tzinfo is None else value.tz_convert(TZ)
        day = pd.Timestamp(local.date())
        distance = abs((day - anchor).days)
        if distance <= 14 and day <= last_day:
            candidates.append((distance, local))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0][1]


def recheck(*, today: object | None = None, reports: pd.DataFrame | None = None,
            fetcher=None, state_path: Path = STATE_FILE, audit_path: Path = AUDIT_FILE,
            auto_path: Path = AUTO_DATES, manual_path: Path = MANUAL_DATES,
            status_path: Path = STATUS_FILE, save: bool = True) -> pd.DataFrame:
    day = pd.Timestamp(today or datetime.now(TZ).date()).normalize()
    current = load_reports() if reports is None else reports.copy()
    state = read_json(state_path, default={})
    manual = verified_date_keys(current, manual_path)
    evidence = date_overrides(auto_path)
    for column in ["published_at", "checked_at"]:
        if column not in evidence:
            evidence[column] = ""
    fetcher = fetcher or (lambda ticker: yf.Ticker(ticker).get_earnings_dates(limit=12, offset=1))
    fetched: dict[str, pd.DataFrame | Exception] = {}
    audit = []
    for idx, report in current.iterrows():
        if not bool(report.verified) or pd.isna(report.effective_date):
            continue
        key = f"{report.ticker}|{report.report_period}"
        entry = state.get(key, {"anchor": pd.Timestamp(report.effective_date).date().isoformat(), "completed": []})
        anchor = pd.Timestamp(entry["anchor"])
        age = (day - anchor).days
        due = [n for n in MILESTONES if age >= n and n not in entry["completed"]]
        if age > WINDOW_DAYS or not due:
            continue
        record = {"checked_at": day.date().isoformat(), "ticker": report.ticker,
                  "report_period": report.report_period, "milestones": "+".join(map(str, due)),
                  "old_date": pd.Timestamp(report.effective_date).date().isoformat(),
                  "new_date": "", "status": "", "detail": ""}
        if (report.ticker, report.report_period) in manual:
            record["status"] = "manual_date_preserved"
            entry["completed"] = sorted(set(entry["completed"] + due))
        else:
            if report.ticker not in fetched:
                try:
                    fetched[report.ticker] = fetcher(report.ticker)
                except Exception as exc:
                    fetched[report.ticker] = exc
            dates = fetched[report.ticker]
            release = None if isinstance(dates, Exception) else select_report_timestamp(dates, anchor, day)
            if release is None:
                record["status"] = "retry_missing_evidence"
                record["detail"] = str(dates)[:200] if isinstance(dates, Exception) else "Ingen entydig rapporthändelse med rapporterad EPS nära datumet."
            else:
                new = effective_date(release)
                record["new_date"] = new.date().isoformat()
                record["status"] = "corrected" if new != pd.Timestamp(report.effective_date) else "confirmed"
                row = {"ticker": report.ticker, "report_period": report.report_period,
                       "report_date": new.date().isoformat(), "source": "Yahoo Finance / earnings date recheck",
                       "published_at": release.isoformat(), "checked_at": day.date().isoformat()}
                keep = ~(evidence.ticker.eq(report.ticker) & evidence.report_period.eq(report.report_period))
                evidence = pd.concat([evidence.loc[keep], pd.DataFrame([row])], ignore_index=True)
                current.at[idx, "effective_date"] = new
                current.at[idx, "published_at"] = release.tz_convert("UTC")
                entry["completed"] = sorted(set(entry["completed"] + due))
        state[key] = entry
        audit.append(record)
        print(f"Rapportdatum {report.ticker} {report.report_period}: {record['status']} ({record['old_date']} -> {record['new_date']}).")

    auto_path.parent.mkdir(parents=True, exist_ok=True)
    evidence.sort_values(["ticker", "report_period"]).to_csv(auto_path, index=False)
    write_json_atomic(state_path, state, pretty=True)
    if audit:
        old = pd.read_csv(audit_path) if audit_path.exists() else pd.DataFrame()
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        pd.concat([old, pd.DataFrame(audit)], ignore_index=True).to_csv(audit_path, index=False)
    counts = pd.Series([item["status"] for item in audit], dtype=str).value_counts().to_dict()
    missing = current.loc[current.effective_date.isna(), ["ticker", "report_period"]].to_dict("records")
    from .events import load_report_calendar
    from .reporting import load_auto_report_calendar, _combined_schedule
    automatic = load_auto_report_calendar()
    schedule = _combined_schedule(automatic, load_report_calendar())
    covered = set(schedule.loc[schedule.report_date_end.ge(day), "ticker"])
    uncovered = sorted(set(current.ticker) - covered)
    conflicts = []
    for ticker, rows in automatic.groupby("ticker"):
        if rows.report_date_start.nunique() > 1:
            conflicts.append({"ticker": str(ticker), "observations": [
                {"source": str(item.source), "date": pd.Timestamp(item.report_date_start).date().isoformat()}
                for item in rows.itertuples(index=False)]})
    write_json_atomic(status_path, {"checked_at": day.date().isoformat(), "counts": counts,
                                   "missing_historical_dates": missing,
                                   "missing_upcoming_tickers": uncovered,
                                   "calendar_source_conflicts": conflicts}, pretty=True)
    if save:
        save_reports(current)
    print(f"Rapportdatumkontroll: {counts}; {len(missing)} historiska poster utan datum.")
    return current


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today")
    args = parser.parse_args()
    recheck(today=args.today)
