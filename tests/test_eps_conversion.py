"""Synthetic examples: FX cutoff, source priority, and per-period provenance."""
import pandas as pd
import pytest

from src.eps_conversion import convert_ttm, native_ttm, conversion_metadata, apply_fx_fallbacks
from src.fundamentals import normalise_reports, empty_reports
from src.earnings import EPS_SOURCE
from src.quarterly_eps import MANUAL_METRIC, DILUTED_METRIC
from src.reporting import _report_eps_change


def fx():
    return pd.DataFrame([dict(date=date, rate=rate, base_currency='EUR', quote_currency='SEK')
                         for date, rate in [('2026-10-30', 10), ('2026-11-02', 11)]])


def report(value=4, source='TradingView / diluted', notes='report_currency=SEK', end='2026-06-30', date='2026-07-20'):
    return normalise_reports(pd.DataFrame([dict(ticker='EXAMPLE.ST', report_period='2026-Q2',
        period_end=end, effective_date=date, published_at=date, eps_ttm=value,
        source=source, verified=True, notes=notes)]))


def quarters():
    return pd.DataFrame([dict(ticker='EXAMPLE.ST',period_end=pd.Timestamp(end),report_date=pd.Timestamp(day) if day else pd.NaT,
        observed_date=pd.Timestamp('2026-11-02'),metric=metric,eps=value,eps_currency='EUR',source='Example issuer')
        for end,day,metric,value in [('2025-09-30',None,MANUAL_METRIC,.2),
                                     ('2025-09-30',None,DILUTED_METRIC,.3),
                                     ('2026-09-30','2026-11-02',MANUAL_METRIC,.5)]])


def earnings():
    return pd.DataFrame([dict(ticker='EXAMPLE.ST',period_end=pd.Timestamp('2026-06-30'),
        observed_date=pd.Timestamp('2026-08-01'),eps_ttm=1,eps_currency='EUR',source=EPS_SOURCE)])


@pytest.mark.parametrize('value', [1, 0, -1])
def test_prior_available_day_is_pinned_and_sign_preserved(value):
    result=convert_ttm(value,'EUR','SEK','2026-11-02',fx())
    assert result['eps_ttm']==value*10  # Monday uses Friday, never Monday close.
    meta=conversion_metadata(result)
    assert meta['rate_date']=='2026-10-30' and meta['original_eps_ttm']==value
    assert conversion_metadata({'notes':'report_currency=SEK'}) is None


def test_missing_stale_and_same_currency_are_not_silently_converted():
    for date,currency in [('2026-10-30','EUR'),('2026-11-20','EUR'),('2026-11-02','SEK')]:
        with pytest.raises(ValueError): convert_ttm(1,currency,'SEK',date,fx())


def test_bridge_uses_native_ttm_and_verified_comparative_not_sek_tv_or_reported_eps():
    result=native_ttm('EXAMPLE.ST','2026-09-30',.5,'EUR',quarters(),earnings(),report(400))
    assert result['eps_ttm']==1.3  # Native 1 + .5 - .2, never 400 + .5 - .3.
    with pytest.raises(ValueError): native_ttm('EXAMPLE.ST','2026-09-30',.5,'USD',quarters(),earnings(),report())
    with pytest.raises(ValueError): native_ttm('EXAMPLE.ST','2026-09-30',.5,'EUR',quarters().iloc[:0],earnings(),report())


def test_conversion_attaches_only_to_its_report_period_and_tv_replacement_clears_it():
    old=report();new=report(13,notes=convert_ttm(1.3,'EUR','SEK','2026-11-02',fx())['notes']+'; report_currency=SEK',end='2026-09-30',date='2026-11-02')
    new.loc[:,'report_period']='2026-Q3'
    all_reports=pd.concat([old,new],ignore_index=True)
    change=_report_eps_change(new.iloc[0],all_reports,pd.DataFrame(),'SEK')
    assert change['eps_ttm_before_conversion'] is None
    assert change['eps_ttm_after_conversion']['rate_date']=='2026-10-30'
    new.loc[:,'notes']='report_currency=SEK'
    assert _report_eps_change(new.iloc[0],pd.concat([old,new]),pd.DataFrame(),'SEK')['eps_ttm_after_conversion'] is None


def test_automatic_fallback_is_idempotent_and_cannot_replace_manual_tv(monkeypatch):
    import src.eps_conversion as conversion
    import src.quarterly_eps as q
    import src.earnings as e
    import src.fx as f
    import src.fundamentals as r
    saved=[]
    monkeypatch.setattr(q,'load_quarterly_eps',quarters)
    monkeypatch.setattr(e,'load_earnings_history',earnings)
    monkeypatch.setattr(f,'load_fx_history',fx)
    monkeypatch.setattr(f,'load_stock_currencies',lambda:pd.DataFrame([dict(ticker='EXAMPLE.ST',price_currency='SEK')]))
    monkeypatch.setattr(r,'save_reports',lambda frame:saved.append(frame))
    monkeypatch.setattr(conversion,'record_conversion',lambda row:None)
    initial=report()
    result=apply_fx_fallbacks(initial,today='2026-11-02')
    assert len(saved)==1 and result.iloc[-1].eps_ttm==13
    assert conversion_metadata(result.iloc[-1])['original_eps_ttm']==1.3
    again=apply_fx_fallbacks(result,today='2026-11-02')
    assert len(saved)==1 and again.equals(result)
    tv=result.copy();tv.loc[tv.report_period.eq('2026-Q3'),'notes']='report_currency=SEK'
    tv.loc[tv.report_period.eq('2026-Q3'),'source']='TradingView / diluted'
    assert apply_fx_fallbacks(tv,today='2026-11-02').equals(tv)


def test_audit_survives_tv_replacement_without_duplicates(tmp_path):
    from src.eps_conversion import record_conversion
    converted=report(13,notes=convert_ttm(1.3,'EUR','SEK','2026-11-02',fx())['notes']).iloc[0]
    path=tmp_path/'conversions.csv'
    record_conversion(converted,path);record_conversion(converted,path)
    assert len(pd.read_csv(path))==1
    tv=converted.copy();tv['notes']='report_currency=SEK'
    record_conversion(tv,path)
    assert pd.read_csv(path).iloc[0].original_eps_ttm==1.3
