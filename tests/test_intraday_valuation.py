"""Synthetic examples: intraday row replacement and report-day EPS changes."""
import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from src.fundamentals import attach_eps_ttm, normalise_reports
from src.intraday_valuation import add_preliminary_scores
from src.model_data import ensure_gbm_model
from src.valuation import GBMModel, calculate_valuation


def example(eps=5.):
    day = pd.Timestamp('2026-10-16')
    dates = xcals.get_calendar('XSTO').sessions
    dates = dates.tz_localize(None) if dates.tz is not None else dates
    dates = dates[dates < day][-240:]
    x = np.arange(len(dates))
    prices = pd.DataFrame({'date': dates, 'close': 100 + 8 * np.sin(x / 11) + x * .08, 'ticker': 'EXAMPLE.ST'})
    reports = normalise_reports(pd.DataFrame([
        {'ticker':'EXAMPLE.ST','period_end':'2025-09-30','report_period':'2025-Q3',
         'effective_date':'2025-10-01','eps_ttm':eps,'verified':True},
        {'ticker':'EXAMPLE.ST','period_end':'2026-09-30','report_period':'2026-Q3',
         'effective_date':'2026-10-16','published_at':'2026-10-16T07:00:00+02:00','eps_ttm':eps * 1.2,'verified':True},
    ]))
    now = datetime(2026,10,16,11,30,tzinfo=ZoneInfo('Europe/Stockholm'))
    stocks = [{'ticker':'EXAMPLE.ST','latest_date':'2026-10-15','currency':'SEK'}]
    cache = {'session_date':'2026-10-16','stocks':{'EXAMPLE.ST':{'latest':{
        'price':110.,'as_of':'2026-10-16T11:10:00+02:00','currency':'SEK'}}}}
    return prices, reports, now, stocks, cache


@pytest.mark.parametrize('eps', [5., -5.])
def test_new_eps_and_repeated_refresh_match_full_engine_without_mutating_history(eps):
    prices, reports, now, stocks, cache = example(eps)
    original_prices, original_reports = prices.copy(deep=True), reports.copy(deep=True)
    model = GBMModel.load(ensure_gbm_model())
    for price in [110., 90., 130.]:
        cache['stocks']['EXAMPLE.ST']['latest']['price'] = price
        add_preliminary_scores(cache, stocks, now, prices=prices, reports=reports, model=model)
        v = cache['stocks']['EXAMPLE.ST']['valuation']
        trial = prices.rename(columns={'date':'Date','close':'Close'})[['Date','Close']]
        trial = pd.concat([trial,pd.DataFrame({'Date':[pd.Timestamp('2026-10-16')],'Close':[price]})],ignore_index=True)
        expected = calculate_valuation(attach_eps_ttm(trial,'EXAMPLE.ST',reports),model=model).Score.iloc[-1]
        assert v['score'] == pytest.approx(expected,abs=.000051)
        assert v['eps_ttm'] == pytest.approx(eps * 1.2)
        assert v['price'] == price
        assert v['basis_date'] == '2026-10-15'
    pd.testing.assert_frame_equal(prices, original_prices)
    pd.testing.assert_frame_equal(reports, original_reports)


def test_invalid_or_incomplete_context_clears_previous_preliminary_score():
    prices, reports, now, stocks, cache = example()
    cache['stocks']['EXAMPLE.ST']['valuation'] = {'score': .5}
    for changed in ['gap','currency','future','zero_eps']:
        payload = copy.deepcopy(cache)
        history, known = prices.copy(), reports.copy()
        if changed == 'gap': history = history.iloc[:-1]
        if changed == 'currency': payload['stocks']['EXAMPLE.ST']['latest']['currency'] = 'EUR'
        if changed == 'future': payload['stocks']['EXAMPLE.ST']['latest']['as_of'] = '2026-10-16T12:00:00+02:00'
        if changed == 'zero_eps': known['eps_ttm'] = 0
        add_preliminary_scores(payload, stocks, now, prices=history, reports=known)
        assert 'valuation' not in payload['stocks']['EXAMPLE.ST']


def test_report_published_after_quote_is_not_used():
    prices, reports, now, stocks, cache = example()
    reports.loc[1,'published_at'] = pd.Timestamp('2026-10-16T10:00:00Z')
    add_preliminary_scores(cache,stocks,now,prices=prices,reports=reports)
    assert cache['stocks']['EXAMPLE.ST']['valuation']['eps_ttm'] == 5.


@pytest.mark.parametrize("fetched,expected", [
    ("2026-10-16T17:29:59+02:00", True),
    ("2026-10-16T17:30:00+02:00", False),
    ("2026-10-16T15:30:00Z", False),
    (None, True),
])
def test_valuation_status_uses_successful_quote_fetch_time(fetched, expected):
    prices, reports, now, stocks, cache = example()
    now = now.replace(hour=20)
    cache["generated_at"] = now.isoformat()
    cache["stocks"]["EXAMPLE.ST"]["latest"]["fetched_at"] = fetched
    add_preliminary_scores(cache, stocks, now, prices=prices, reports=reports)
    assert cache["stocks"]["EXAMPLE.ST"]["valuation"]["preliminary"] is expected
