"""Synthetic examples for report-date corrections and protected history."""
from pathlib import Path

import pandas as pd

from src.fundamentals import normalise_reports
from src.report_date_revisions import apply_date_evidence, changed_date_cutoffs
from src.recheck_report_dates import recheck, effective_date, select_report_timestamp
from src.score_history import apply_frozen_scores


def reports(day='2026-09-03'):
    return normalise_reports(pd.DataFrame([dict(ticker='EXAMPLE.ST', report_period='2026-Q3',
        period_end='2026-07-31', effective_date=day, eps_ttm=12.3456789,
        source='TradingView / manual EPS', verified=True)]))


def test_stockholm_date_and_after_close_use_actual_exchange_session():
    assert effective_date('2026-09-02T22:00:00-04:00') == pd.Timestamp('2026-09-03')
    assert effective_date('2026-09-04T18:00:00+02:00') == pd.Timestamp('2026-09-07')
    # Stockholm closes at 13:00 on this half-day.
    assert effective_date('2026-01-05T14:00:00+01:00') == pd.Timestamp('2026-01-07')


def test_rebase_uses_earlier_date_and_preserves_all_earlier_scores():
    previous = reports('2026-09-03')
    current = reports('2026-09-02')
    assert changed_date_cutoffs(current, previous) == {'EXAMPLE.ST': pd.Timestamp('2026-09-02')}
    assert changed_date_cutoffs(previous, current) == {'EXAMPLE.ST': pd.Timestamp('2026-09-02')}
    history = pd.DataFrame([dict(ticker='EXAMPLE.ST', date='2026-09-01', score=20),
                            dict(ticker='EXAMPLE.ST', date='2026-09-02', score=30)])
    valued = pd.DataFrame({'Date': ['2026-09-01', '2026-09-02'], 'Score': [99, 80]})
    result, additions = apply_frozen_scores(valued, 'EXAMPLE.ST', history,
                         frozen_at='example', recalculate_from='2026-09-02')
    assert result.Score.tolist() == [20, 80]
    assert additions.date.tolist() == [pd.Timestamp('2026-09-02')]


def paths(tmp_path):
    return dict(state_path=tmp_path/'state.json', audit_path=tmp_path/'audit.csv',
                auto_path=tmp_path/'auto.csv', manual_path=tmp_path/'manual.csv',
                status_path=tmp_path/'status.json', save=False)


def test_date_only_change_is_detected_with_unchanged_manual_eps_and_second_check(tmp_path):
    args = paths(tmp_path)
    calls = []
    def fetch(ticker):
        calls.append(ticker)
        return pd.DataFrame({'Reported EPS': [2]}, index=[pd.Timestamp('2026-09-04T07:00:00+02:00')])
    first = recheck(today='2026-09-10', reports=reports(), fetcher=fetch, **args)
    assert first.effective_date.iloc[0] == pd.Timestamp('2026-09-04')
    assert first.eps_ttm.iloc[0] == 12.3456789
    assert first.source.iloc[0] == 'TradingView / manual EPS'
    recheck(today='2026-09-11', reports=first, fetcher=fetch, **args)
    assert len(calls) == 1
    # Milestone remains anchored to original release; moving the date doesn't postpone it.
    recheck(today='2026-09-17', reports=first, fetcher=fetch, **args)
    assert len(calls) == 2
    audit = pd.read_csv(args['audit_path'])
    assert audit.milestones.astype(str).tolist() == ['0+7', '14']


def test_missing_evidence_retries_and_does_not_shift_existing_date(tmp_path):
    args = paths(tmp_path)
    first = recheck(today='2026-09-10', reports=reports(), fetcher=lambda _: None, **args)
    assert first.effective_date.iloc[0] == pd.Timestamp('2026-09-03')
    dates = pd.DataFrame({'Reported EPS': [2]}, index=[pd.Timestamp('2026-09-04T07:00:00+02:00')])
    second = recheck(today='2026-09-11', reports=first, fetcher=lambda _: dates, **args)
    assert second.effective_date.iloc[0] == pd.Timestamp('2026-09-04')


def test_user_date_has_priority_over_recheck_and_import(tmp_path):
    args = paths(tmp_path)
    pd.DataFrame([dict(ticker='EXAMPLE.ST',report_period='2026-Q3',report_date='2026-09-03',source='User')]).to_csv(args['manual_path'], index=False)
    def fail(_):
        raise AssertionError('Pinned dates must not request Yahoo')
    recheck(today='2026-09-18', reports=reports(), fetcher=fail, **args)
    overwritten = reports('2026-09-02')
    corrected = apply_date_evidence(overwritten, manual_path=args['manual_path'], auto_path=args['auto_path'])
    assert corrected.effective_date.iloc[0] == pd.Timestamp('2026-09-03')
    assert corrected.eps_ttm.iloc[0] == 12.3456789


def test_wrong_quarter_and_future_dates_are_not_used():
    dates = pd.DataFrame({'Reported EPS': [1, 2]}, index=pd.to_datetime(['2026-06-03', '2026-12-03']))
    assert select_report_timestamp(dates, '2026-09-03', '2026-09-18') is None


def test_new_date_and_removed_report_are_rebased():
    old = reports('2026-09-03')
    assert changed_date_cutoffs(old.iloc[:0], old) == {'EXAMPLE.ST': pd.Timestamp('2026-09-03')}
    blank = reports(None)
    assert changed_date_cutoffs(old, blank) == {'EXAMPLE.ST': pd.Timestamp('2026-09-03')}


def test_manual_future_date_suppresses_conflicting_automatic_date():
    from src.reporting import _combined_schedule
    from src.events import load_report_calendar
    auto = pd.DataFrame([dict(ticker='EXAMPLE.ST',report_date_start='2026-10-22',
            report_date_end='2026-10-22',observed_date='2026-10-04',source='Yahoo Finance / calendarEvents')])
    manual = load_report_calendar().iloc[:0].copy()
    manual = pd.concat([manual,pd.DataFrame([dict(ticker='EXAMPLE.ST', report_period='2026-Q3',
        scheduled_at=pd.Timestamp('2026-10-23T07:00:00+02:00'),lock_from_date=pd.NaT,
        source='Synthetic user example',url='',verified=True,expected_eps=None,
        expected_eps_currency='',expected_eps_metric='',expected_eps_verified=False)])],ignore_index=True)
    rows = _combined_schedule(auto,manual)
    assert len(rows) == 1
    assert rows.report_date_start.iloc[0] == pd.Timestamp('2026-10-23')


def test_initial_date_check_runs_without_waiting_for_eps_change(tmp_path):
    args = paths(tmp_path)
    dates = pd.DataFrame({'Reported EPS': [2]},
                         index=[pd.Timestamp('2026-09-03T07:00:00+02:00')])
    # Example: Yahoo expressed the Swedish release on the preceding calendar day.
    result = recheck(today='2026-09-03', reports=reports('2026-09-02'),
                     fetcher=lambda _: dates, **args)
    assert result.effective_date.iloc[0] == pd.Timestamp('2026-09-03')
    assert result.eps_ttm.iloc[0] == 12.3456789
    assert pd.read_csv(args['audit_path']).milestones.iloc[0] == 0
