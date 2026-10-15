"""Flag scheduled reports whose new valuation EPS has not arrived."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import load_reports
from .listing_status import active_tickers


def report_data_status(reports: pd.DataFrame, *, today: object,
                       events: pd.DataFrame | None = None,
                       checks: pd.DataFrame | None = None) -> dict[str, object]:
    from .reporting import CALENDAR_HISTORY_FILE, _combined_schedule, load_auto_report_calendar
    from .events import load_report_calendar

    day = pd.Timestamp(today)
    if day.tzinfo is not None:
        day = day.tz_convert('Europe/Stockholm').tz_localize(None)
    day = day.normalize()
    if events is None:
        current = _combined_schedule(load_auto_report_calendar(), load_report_calendar())
        history = load_auto_report_calendar(CALENDAR_HISTORY_FILE)
        # Prefer the current source/manual date over superseded forecasts for
        # the same reporting cycle, while retaining earlier overdue cycles.
        for row in current.itertuples(index=False):
            history = history.loc[~(history.ticker.eq(row.ticker) &
                history.report_date_start.sub(row.report_date_start).abs().le(pd.Timedelta(days=45)))]
        events = pd.concat([frame for frame in (current, history) if not frame.empty], ignore_index=True) if not current.empty or not history.empty else current.copy()
        events = events.rename(columns={'report_date_end': 'report_date'})
    events = events.copy()
    events['report_date'] = pd.to_datetime(events['report_date'], errors='coerce').dt.normalize()
    events = events.loc[events['report_date'].le(day)]
    events = events.sort_values('report_date').drop_duplicates('ticker', keep='last')
    events = events.loc[events.ticker.isin(active_tickers(events.ticker, today=day))]
    if checks is None:
        path = ROOT / 'data/manual/report_data_checks.csv'
        checks = pd.read_csv(path, dtype=str).fillna('') if path.exists() else pd.DataFrame()
    missing, without_eps = [], []
    for event in events.itertuples(index=False):
        ticker, date = str(event.ticker), pd.Timestamp(event.report_date)
        rows = reports.loc[reports.ticker.astype(str).eq(ticker)].copy()
        rows['effective_date'] = pd.to_datetime(rows.effective_date, errors='coerce').dt.normalize()
        rows['period_end'] = pd.to_datetime(rows.period_end, errors='coerce').dt.normalize()
        rows = rows.loc[rows.verified.astype(str).str.lower().isin(['true', '1']) & pd.to_numeric(rows.eps_ttm, errors='coerce').notna()]
        baseline = rows.loc[rows.effective_date.lt(date), 'period_end'].max()
        fresh = rows.loc[rows.effective_date.ge(date) & rows.effective_date.le(day)
                         & rows.period_end.le(date) & rows.period_end.ge(date - pd.Timedelta(days=140))]
        if pd.notna(baseline):
            fresh = fresh.loc[fresh.period_end.gt(baseline)]
        if not fresh.empty:
            continue
        item = {'ticker': ticker, 'report_date': date.date().isoformat(),
                'days_since_report': int((day - date).days), 'status': 'missing_eps',
                'message': 'EPS-data saknas efter rapportdatum. Värderingen använder äldre rapportdata.'}
        if not checks.empty:
            evidence = checks.loc[checks.ticker.eq(ticker) & checks.report_date.eq(item['report_date'])
                                  & checks.status.eq('published_without_eps')]
            if not evidence.empty:
                item.update(status='published_without_eps', message='Publicerad redogörelse utan EPS. Tidigare EPS TTM behålls.')
                without_eps.append(item)
                continue
        missing.append(item)
    return {'data_checked_at': day.date().isoformat(), 'missing_data': sorted(missing, key=lambda r: (r['report_date'], r['ticker'])),
            'reports_without_eps': without_eps, 'has_missing_report_data': bool(missing)}


def main() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .utils import write_json_atomic
    path = ROOT / 'docs/data/reports.json'
    payload = json.loads(path.read_text())
    status = report_data_status(load_reports(), today=datetime.now(ZoneInfo('Europe/Stockholm')))
    payload.update(status)
    write_json_atomic(path, payload)
    lines = ['## Rapportdata', f"Kontrollerat: {status['data_checked_at']}", '']
    for item in status['missing_data']:
        message = f"{item['ticker']} – rapportdatum {item['report_date']}: EPS-data saknas; äldre data används."
        print(f'::warning::{message}')
        lines.append('- VARNING: ' + message)
    if not status['missing_data']:
        lines.append('Inga rapporter med förväntad EPS saknar nya EPS-data.')
    for item in status['reports_without_eps']:
        lines.append(f"- {item['ticker']} ({item['report_date']}): publicerad redogörelse utan EPS.")
    summary = '\n'.join(lines) + '\n'
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:
            stream.write(summary)


if __name__ == '__main__':
    main()
