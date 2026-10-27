"""Synthetic fixtures for report EPS; model calculation state is never evidence."""
import pandas as pd
import pytest
from src.fundamentals import normalise_reports, save_reports, load_reports
from src.reporting import _report_eps_change, _recent_rows
from src.quarterly_eps import DILUTED_METRIC


def reports(old=4.0, new=5.0):
    return normalise_reports(pd.DataFrame([
        dict(ticker='EXAMPLE.ST', period_end=end, report_period=period, effective_date=date,
             published_at=date+'T07:00:00Z', eps_ttm=eps, verified=True,
             source='TradingView', notes='report_currency=SEK')
        for end,period,date,eps in [('2026-06-30','2026-Q2','2026-07-15',old),
                                   ('2026-09-30','2026-Q3','2026-10-15',new)]
    ]))


def change(data, quarterly=None):
    return _report_eps_change(data.iloc[-1], data, pd.DataFrame() if quarterly is None else quarterly, 'EUR')


@pytest.mark.parametrize('old,new', [(4,5),(0,5),(-2,-1),(4,4)])
def test_distinct_stored_periods_even_when_unchanged(old,new):
    result=change(reports(old,new))
    assert result['eps_ttm_before']==old
    assert result['eps_ttm_after']==new
    assert result['eps_ttm_before_period'] != result['eps_ttm_after_period']


def test_missing_history_and_missing_new_eps_are_not_current_value():
    assert change(reports().iloc[1:])['eps_ttm_before'] is None
    assert change(reports(new=None))['eps_ttm_after'] is None


def test_original_currency_and_manual_sek_are_preserved():
    data=reports(); data.loc[1,'notes']='report_currency=EUR'
    result=change(data)
    assert result['eps_ttm_before_currency']=='SEK'
    assert result['eps_ttm_after_currency']=='EUR'
    assert result['eps_ttm_before']==4


def test_next_report_survives_save_reload_without_overwriting_previous(tmp_path):
    data=reports(); path=tmp_path/'reports.csv'; save_reports(data,path)
    loaded=load_reports(path,cache_path=tmp_path/'no-cache.csv')
    assert change(loaded)['eps_ttm_before']==4
    future=loaded.iloc[-1].to_dict(); future.update(report_period='2026-Q4',period_end='2026-12-31',
        effective_date='2027-01-20',published_at='2027-01-20T07:00:00Z',eps_ttm=6)
    save_reports(pd.concat([loaded,pd.DataFrame([future])]),path)
    loaded=load_reports(path,cache_path=tmp_path/'no-cache.csv')
    assert list(loaded.eps_ttm)==[4,5,6]
    assert change(loaded)['eps_ttm_before']==5
    assert change(loaded.iloc[:2])['eps_ttm_before']==4


def test_four_quarter_fallback_requires_complete_comparable_observed_data():
    q=pd.DataFrame([dict(ticker='EXAMPLE.ST',period_end=end,observed_date='2026-07-20',
        metric=DILUTED_METRIC,eps=1,eps_currency='SEK')
        for end in ['2025-09-30','2025-12-31','2026-03-31','2026-06-30']])
    data=reports().iloc[1:]
    assert change(data,q)['eps_ttm_before']==4
    assert change(data,q.iloc[1:])['eps_ttm_before'] is None
    q.loc[0,'eps_currency']='EUR'
    assert change(data,q)['eps_ttm_before'] is None
    q.loc[0,'eps_currency']='SEK'; q.loc[0,'observed_date']='2026-10-16'
    assert change(data,q)['eps_ttm_before'] is None


def test_report_eps_available_before_new_closing_price():
    result=_recent_rows(reports=reports(),quarterly=pd.DataFrame(),valuation_frames={},
        metadata=pd.DataFrame(columns=['ticker','company','price_currency','report_currency']),as_of=pd.Timestamp('2026-10-15'))
    assert len(result)==1
    assert result[0]['eps_ttm_before']==4 and result[0]['eps_ttm_after']==5
    assert result[0]['score_after'] is None
