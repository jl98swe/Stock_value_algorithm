"""Synthetic reports verify currency conversion in chart report markers."""
import pandas as pd

from src.fundamentals import normalise_reports
from src.pipeline import _report_events


def fixture(currency='EUR'):
    reports=normalise_reports(pd.DataFrame([dict(ticker='EXAMPLE.ST',report_period='2026-Q3',
        period_end='2026-09-30',published_at='2026-10-15T07:00:00+02:00',effective_date='2026-10-15',
        eps_ttm=1.37,source='Example issuer | https://example.test/report',verified=True,
        notes=f'report_currency={currency}')]))
    metadata=pd.DataFrame([dict(ticker='EXAMPLE.ST',price_currency='SEK',report_currency='EUR')])
    fx=pd.DataFrame([dict(date=day,base_currency='EUR',quote_currency='SEK',rate=rate,yahoo_ticker='EURSEK=X')
                     for day,rate in [('2026-10-14',10.0),('2026-10-15',20.0)]])
    return reports,metadata,fx


def test_report_marker_uses_model_currency_and_same_fx_cutoff():
    reports,metadata,fx=fixture()
    event=_report_events(reports,stock_metadata=metadata,fx_history=fx)[0]
    assert event['eps_ttm']==13.700000000000001
    assert event['eps_currency']=='SEK'
    assert event['report_period']=='2026-Q3'
    assert reports.iloc[0].eps_ttm==1.37


def test_already_converted_tradingview_eps_is_not_converted_again():
    reports,metadata,fx=fixture('SEK')
    event=_report_events(reports,stock_metadata=metadata,fx_history=fx)[0]
    assert event['eps_ttm']==1.37
    assert event['eps_currency']=='SEK'


def test_missing_fx_does_not_show_eur_as_sek():
    reports,metadata,fx=fixture()
    event=_report_events(reports,stock_metadata=metadata,fx_history=fx.iloc[:0])[0]
    assert event['eps_ttm'] is None
    assert event['eps_currency']=='SEK'
