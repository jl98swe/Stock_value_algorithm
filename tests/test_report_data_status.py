"""Synthetic report fixtures for missing-data warnings."""
import pandas as pd

from src.report_data_status import report_data_status


def reports(new=True, value=3.0):
    rows=[dict(ticker='ERIC-B.ST', effective_date='2026-07-14', period_end='2026-06-30', eps_ttm=value, verified=True)]
    if new:
        rows.append(dict(ticker='ERIC-B.ST', effective_date='2026-10-15', period_end='2026-09-30', eps_ttm=value, verified=True))
    return pd.DataFrame(rows)


def status(frame, date='2026-10-15', ticker='ERIC-B.ST', checks=None, report_date='2026-10-15'):
    return report_data_status(frame, today=date, events=pd.DataFrame([dict(ticker=ticker, report_date=report_date)]), checks=pd.DataFrame() if checks is None else checks)


def test_missing_report_warns_even_with_old_eps():
    result=status(reports(False))
    assert result['has_missing_report_data']
    assert result['missing_data'][0]['report_date']=='2026-10-15'


def test_new_period_clears_warning_even_with_unchanged_eps():
    assert not status(reports())['missing_data']


def test_unverified_or_future_data_does_not_clear_warning():
    frame=reports();frame.loc[1,'verified']=False
    assert status(frame)['missing_data']
    frame=reports();frame.loc[1,'effective_date']='2026-10-16'
    assert status(frame)['missing_data']


def test_future_report_is_not_missing_and_old_value_redated_is_not_new():
    assert not status(reports(False),date='2026-10-14')['missing_data']
    frame=reports();frame.loc[1,'period_end']='2026-06-30'
    assert status(frame)['missing_data']


def test_no_eps_exception_only_matches_its_report_date():
    frame=reports(False);frame.ticker='EQT.ST'
    checks=pd.DataFrame([dict(ticker='EQT.ST',report_date='2026-10-15',status='published_without_eps')])
    result=status(frame,ticker='EQT.ST',checks=checks)
    assert not result['missing_data'] and result['reports_without_eps']
    result=status(frame,ticker='EQT.ST',checks=checks,date='2027-01-22',report_date='2027-01-22')
    assert result['missing_data'] and not result['reports_without_eps']


def test_stockholm_day_and_weekend_do_not_hide_missing_data():
    assert status(reports(False), date='2026-10-14T22:30:00Z')['missing_data']
    assert status(reports(False), date='2026-10-17')['missing_data']
