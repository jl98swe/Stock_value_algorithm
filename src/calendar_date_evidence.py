"""Resolve publication dates from calendars independently of EPS observations."""
from pathlib import Path
import pandas as pd
from .config import ROOT

CALENDAR_FILES = (ROOT/'data/earnings/report_calendar_history.csv',
                  ROOT/'data/earnings/report_calendar.csv')
MANUAL_CALENDAR = ROOT/'data/manual/report_calendar.csv'


def calendar_dates(reports, *, paths=CALENDAR_FILES, manual_path=MANUAL_CALENDAR,
                   today=None):
    day = pd.Timestamp(today or pd.Timestamp.now(tz='Europe/Stockholm').date()).normalize()
    frames = [pd.read_csv(p).fillna('') for p in paths if Path(p).exists()]
    calendar = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    manual = pd.read_csv(manual_path).fillna('') if Path(manual_path).exists() else pd.DataFrame()
    result = []
    for r in reports.itertuples(index=False):
        anchor = pd.to_datetime(r.effective_date, errors='coerce')
        if pd.isna(anchor):
            continue
        if not manual.empty:
            selected = manual.loc[manual.ticker.eq(r.ticker) & manual.report_period.isin([r.report_period, f'{pd.Timestamp(r.period_end).year}-Q{pd.Timestamp(r.period_end).quarter}'])
                                  & manual.verified.astype(str).str.lower().eq('true')]
            if not selected.empty:
                value = pd.Timestamp(selected.iloc[-1].scheduled_at)
                value = value.tz_localize('Europe/Stockholm') if value.tzinfo is None else value.tz_convert('Europe/Stockholm')
                result.append(dict(ticker=r.ticker, report_period=r.report_period,
                    report_date=value.date().isoformat(), source=str(selected.iloc[-1].source)))
                continue
        if calendar.empty:
            continue
        rows = calendar.loc[calendar.ticker.eq(r.ticker)].copy()
        observed = pd.to_datetime(rows.observed_date, errors='coerce')
        rows = rows.loc[observed.isna() | observed.le(day)]
        start = pd.to_datetime(rows.report_date_start, errors='coerce')
        end = pd.to_datetime(rows.report_date_end, errors='coerce')
        # Only exact, confirmed dates for the same release; never match a future
        # quarter or infer publication from the EPS period end.
        rows = rows.loc[rows.date_status.eq('confirmed') & start.eq(end)
                        & start.gt(pd.Timestamp(r.period_end))
                        & (start-anchor).abs().le(pd.Timedelta(days=21))].copy()
        if rows.empty:
            continue
        rows['rank'] = rows.source.map(lambda s: 0 if str(s).startswith('MFN') else
                                      1 if str(s).startswith('Börskollen') else
                                      2 if str(s).startswith('Yahoo Finance / calendar') else 99)
        rows = rows.loc[rows['rank'].eq(rows['rank'].min()) & rows['rank'].lt(99)]
        if rows.empty:
            continue
        # A more recently observed calendar revision supersedes an older plan.
        observed = pd.to_datetime(rows.observed_date, errors='coerce')
        rows = rows.loc[observed.eq(observed.max())] if observed.notna().any() else rows
        if rows.report_date_start.nunique() != 1:
            raise ValueError(f'Motstridiga rapportkalendrar: {r.ticker} {r.report_period}')
        selected = rows.iloc[-1]
        result.append(dict(ticker=r.ticker, report_period=r.report_period,
                           report_date=selected.report_date_start, source=selected.source))
    return pd.DataFrame(result, columns=['ticker','report_period','report_date','source'])
