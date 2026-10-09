"""Synthetic calendar fixtures for homepage report status."""
import pandas as pd
import pytest

from src import pipeline
from src.events import load_report_calendar
from src.fundamentals import normalise_reports
from src.reporting import _combined_schedule, _normalise_calendar


def manual_calendar(tmp_path, scheduled=None, verified=True):
    path = tmp_path / 'manual.csv'
    pd.DataFrame([{
        'ticker':'AAK.ST', 'scheduled_at':scheduled, 'verified':verified,
        'source':'Manual', 'report_period':'2026-Q3',
    }] if scheduled else [], columns=['ticker','scheduled_at','verified','source','report_period']).to_csv(path,index=False)
    return load_report_calendar(path)


def automatic(start='2026-10-23', end=None):
    return _normalise_calendar(pd.DataFrame([{
        'ticker':'AAK.ST', 'report_date_start':start, 'report_date_end':end or start,
        'date_status':'estimated_range' if end and end != start else 'confirmed',
        'source':'Yahoo Finance / calendarEvents', 'observed_date':'2026-10-08',
    }]))


def payload(manual, auto, day='2026-10-09'):
    return pipeline._report_payload('AAK.ST', normalise_reports(pd.DataFrame()), manual,
        schedule=_combined_schedule(auto,manual), as_of=pd.Timestamp(day))


def test_automatic_date_used_when_no_manual_date(tmp_path):
    result = payload(manual_calendar(tmp_path), automatic())
    assert result['next_report'] == '2026-10-23'
    assert result['next_report_end'] == '2026-10-23'
    assert result['next_report_source'] == 'Yahoo Finance / calendarEvents'


@pytest.mark.parametrize('verified',[True,False])
def test_manual_date_overrides_conflicting_automatic_date(tmp_path,verified):
    result = payload(manual_calendar(tmp_path,'2026-10-26',verified), automatic())
    assert result['next_report'] == '2026-10-26'
    assert result['next_report_source'] == 'Manual'
    assert result['next_report_status'] == ('verified_manual' if verified else 'manual')


def test_old_manual_report_does_not_hide_next_quarter(tmp_path):
    assert payload(manual_calendar(tmp_path,'2026-07-17'),automatic())['next_report'] == '2026-10-23'


def test_same_day_report_remains_visible_and_uses_stockholm_date(tmp_path):
    # 22:30 UTC is already the following day in Sweden.
    result = payload(manual_calendar(tmp_path,'2026-10-08T22:30:00Z'),automatic('2026-10-09'))
    assert result['next_report'] == '2026-10-09'
    assert payload(manual_calendar(tmp_path),automatic('2026-10-08'))['next_report'] is None


def test_estimated_range_is_preserved_and_expired_range_is_excluded(tmp_path):
    result = payload(manual_calendar(tmp_path),automatic('2026-10-08','2026-10-12'))
    assert result['next_report'] == '2026-10-08'
    assert result['next_report_end'] == '2026-10-12'
    assert result['next_report_status'] == 'estimated_range'
    assert payload(manual_calendar(tmp_path),automatic('2026-10-08','2026-10-12'),'2026-10-13')['next_report'] is None


def test_default_export_uses_automatic_calendar(tmp_path,monkeypatch):
    monkeypatch.setattr(pipeline,'load_auto_report_calendar',lambda:automatic('2099-10-23'))
    result = pipeline._report_payload('AAK.ST',normalise_reports(pd.DataFrame()),manual_calendar(tmp_path))
    assert result['next_report'] == '2099-10-23'


def test_refresh_changes_only_upcoming_fields_in_both_exports(tmp_path):
    import json
    from src.refresh_home_report_status import refresh_report_status
    original = {'report':{'period':'2026-Q2','eps_ttm':7.123456,'verified':True,'next_report':None},
        'latest':{'score':42.5,'close':100}, 'candles':[{'date':'2026-10-08','close':100}]}
    target = tmp_path / 'dashboard.json'
    target.write_text(json.dumps({'meta':{'generated_at':'unchanged'},'stocks':{'AAK.ST':original}}))
    split_dir = tmp_path / 'dashboard'
    split_dir.mkdir()
    (split_dir / 'AAK.ST.json').write_text(json.dumps(original))
    schedule = _combined_schedule(automatic(), manual_calendar(tmp_path))
    assert refresh_report_status(target,schedule=schedule,as_of=pd.Timestamp('2026-10-09')) == 1
    combined = json.loads(target.read_text())
    stock = combined['stocks']['AAK.ST']
    assert stock == json.loads((split_dir / 'AAK.ST.json').read_text())
    assert stock['report']['next_report'] == '2026-10-23'
    stock['report'] = {key:value for key,value in stock['report'].items() if not key.startswith('next_report')}
    expected = {**original,'report':{key:value for key,value in original['report'].items() if not key.startswith('next_report')}}
    assert stock == expected
    assert combined['meta'] == {'generated_at':'unchanged'}
    assert refresh_report_status(target,schedule=schedule,as_of=pd.Timestamp('2026-10-09')) == 0
