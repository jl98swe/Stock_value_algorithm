from pathlib import Path

import exchange_calendars as xcals
import pandas as pd
import pytest

from src.fundamentals import (attach_eps_ttm, load_reports, normalise_reports,
                              save_reports, valuation_calculation_mode, REPORT_DATE_STATE, TV_PERIOD_END_STATE)
from src.report_publications import (PUBLICATIONS, apply_publications, publication_metadata,
                                     publication_session, AFTER_CLOSE_NOTE)
from src.report_date_revisions import apply_date_evidence, score_snapshot


@pytest.mark.parametrize('at,expected', [
    ('2026-11-04T15:30:00-08:00', '2026-11-05'),
    ('2024-05-01T14:30:00-08:00', '2024-05-02'),
    ('2026-11-06T18:00:00+01:00', '2026-11-09'),
    ('2024-12-23T18:00:00+01:00', '2024-12-27'),
    ('2026-11-05T08:00:00+01:00', '2026-11-05'),
])
def test_first_available_swedish_session(at, expected):
    assert publication_session(at)[0] == pd.Timestamp(expected)


def test_half_day_uses_actual_close():
    cal = xcals.get_calendar('XSTO')
    close = cal.session_close('2024-04-30')
    assert close.tz_convert('Europe/Stockholm').hour == 13
    assert publication_session(close - pd.Timedelta(seconds=1))[0] == pd.Timestamp('2024-04-30')
    assert publication_session(close)[0] == pd.Timestamp('2024-05-02')


def test_naive_publication_rejected():
    with pytest.raises(ValueError, match='timezone'):
        publication_session('2026-11-04T15:30:00')


def test_all_lumi_reports_verified_and_no_future_eps():
    reports = load_reports()
    lumi = reports.loc[reports.ticker.eq('LUMI.ST')].sort_values('effective_date')
    evidence = pd.read_csv(PUBLICATIONS)
    assert len(lumi) == len(evidence) == 33
    assert set(lumi.report_period) == set(evidence.report_period)
    assert lumi.publication_time_verified.all()
    assert valuation_calculation_mode('LUMI.ST', reports) == REPORT_DATE_STATE
    assert score_snapshot(reports).loc[reports.ticker.eq('LUMI.ST'), 'calculation_mode'].eq(REPORT_DATE_STATE).all()
    dates = pd.date_range('2018-09-01', '2026-11-06')
    # Even a caller explicitly requesting TV calibration cannot move verified releases earlier.
    result = attach_eps_ttm(pd.DataFrame({'Date': dates}), 'LUMI.ST', reports,
                           stock_metadata=pd.DataFrame(), calculation_mode=TV_PERIOD_END_STATE)
    for row in lumi.itertuples():
        first = result.loc[result.Date.eq(row.effective_date), 'EPS_TTM'].iloc[0]
        assert first == row.eps_ttm
        previous = lumi.loc[lumi.effective_date.lt(row.effective_date)].tail(1)
        before = result.loc[result.Date.eq(row.effective_date - pd.Timedelta(days=1)), 'EPS_TTM'].iloc[0]
        assert pd.isna(before) if previous.empty else before == previous.iloc[0].eps_ttm
        assert pd.Timestamp(row.published_at) <= xcals.get_calendar('XSTO').session_close(row.effective_date)


def test_calendar_cannot_overwrite_verified_publication(tmp_path, monkeypatch):
    from src import calendar_date_evidence
    reports = load_reports()
    lumi = reports.loc[reports.ticker.eq('LUMI.ST') & reports.report_period.eq('2026-Q3')]
    fake = pd.DataFrame([dict(ticker='LUMI.ST', report_period='2026-Q3', report_date='2026-11-04')])
    monkeypatch.setattr(calendar_date_evidence, 'calendar_dates', lambda reports: fake)
    path = tmp_path / 'missing.csv'
    result = apply_date_evidence(lumi, manual_path=path, auto_path=path)
    row = result.iloc[0]
    assert row.effective_date == pd.Timestamp('2026-11-05')
    assert row.published_at == pd.Timestamp('2026-11-04T23:30:00Z')
    assert row.eps_ttm == lumi.iloc[0].eps_ttm
    assert row.source == lumi.iloc[0].source
    output = tmp_path / 'reports.csv'
    save_reports(result, output)
    again = load_reports(output, cache_path=path).iloc[0]
    assert again.publication_time_verified
    assert again.report_date == pd.Timestamp('2026-11-04')
    assert again.effective_date == row.effective_date


def test_official_date_retained_after_swedish_midnight():
    reports = load_reports()
    row = reports.loc[reports.ticker.eq('LUMI.ST') & reports.report_period.eq('2025-Q2')].iloc[0]
    info = publication_metadata(row)
    assert info['report_date'] == '2025-08-06'
    assert row.effective_date == pd.Timestamp('2025-08-07')
    assert info['publication_note'] == AFTER_CLOSE_NOTE
    assert info['published_after_close']
    assert publication_metadata({'published_at': '2026-11-04T23:30:00Z'})['publication_note'] is None


def test_future_eps_cannot_change_published_score_prefix():
    import numpy as np
    from src.valuation import GBMModel, calculate_valuation
    dates = pd.bdate_range('2025-01-01', '2026-11-06')
    frame = pd.DataFrame({'Date': dates, 'Close': 100 + np.arange(len(dates)) / 10})
    reports = normalise_reports(pd.DataFrame([
        dict(ticker='EXAMPLE.ST', report_period='2025-Q1', period_end='2025-03-31',
             effective_date='2025-05-01', eps_ttm=5, verified=True, publication_time_verified=True),
        dict(ticker='EXAMPLE.ST', report_period='2026-Q3', period_end='2026-09-30',
             effective_date='2026-11-05', eps_ttm=10, verified=True, publication_time_verified=True),
    ]))
    model = GBMModel.load()
    def valued(r):
        return calculate_valuation(attach_eps_ttm(frame, 'EXAMPLE.ST', r,
            stock_metadata=pd.DataFrame(), calculation_mode=TV_PERIOD_END_STATE), model=model)
    before = valued(reports)
    reports.loc[reports.report_period.eq('2026-Q3'), 'eps_ttm'] = 20
    after = valued(reports)
    prefix = dates < pd.Timestamp('2026-11-05')
    np.testing.assert_allclose(before.loc[prefix, 'Score'], after.loc[prefix, 'Score'], equal_nan=True)
