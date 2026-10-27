"""Synthetic examples of calendar/EPS date conflicts."""
import pandas as pd
import pytest
from src.calendar_date_evidence import calendar_dates
from src.fundamentals import normalise_reports
from src.report_date_revisions import apply_date_evidence


def fixture(tmp_path, monkeypatch, rows):
    import src.calendar_date_evidence as module
    reports = normalise_reports(pd.DataFrame([dict(ticker='EXAMPLE.ST',
        report_period='YAHOO-2026-09-30', period_end='2026-09-30',
        effective_date='2026-10-22', published_at='2026-10-22T06:00:00Z',
        eps_ttm=5.25, source='Yahoo Finance / trailingDilutedEPS', verified=True)]))
    path=tmp_path/'calendar.csv'
    pd.DataFrame([dict(ticker='EXAMPLE.ST', report_date_start=date,
        report_date_end=date, date_status='confirmed', source=source,
        observed_date=observed) for date,source,observed in rows]).to_csv(path,index=False)
    def resolve(frame, **kwargs):
        return calendar_dates(frame, paths=[path], manual_path=tmp_path/'manual-calendar.csv',
                              today=kwargs.get('today','2026-10-27'))
    monkeypatch.setattr(module,'calendar_dates',resolve)
    return reports, resolve


def test_calendar_wins_without_changing_eps_and_recheck_cannot_replace_it(tmp_path, monkeypatch):
    reports,_=fixture(tmp_path,monkeypatch,[('2026-10-23','MFN / bolagets rapportkalender','2026-10-09'),
        ('2026-10-22','Yahoo Finance / calendarEvents','2026-10-26')])
    auto=tmp_path/'auto.csv'; manual=tmp_path/'manual.csv'
    corrected=apply_date_evidence(reports,auto_path=auto,manual_path=manual)
    assert corrected.effective_date.iloc[0] == pd.Timestamp('2026-10-23')
    assert pd.isna(corrected.published_at.iloc[0])
    assert corrected.eps_ttm.tolist() == reports.eps_ttm.tolist()
    from src.recheck_report_dates import recheck
    def fail(_): raise AssertionError('Calendar-covered release must not request Yahoo EPS dates')
    result=recheck(today='2026-10-27',reports=reports,fetcher=fail,auto_path=auto,manual_path=manual,
        state_path=tmp_path/'state.json',audit_path=tmp_path/'audit.csv',status_path=tmp_path/'status.json',save=False)
    assert result.effective_date.iloc[0] == pd.Timestamp('2026-10-23')
    assert pd.read_csv(tmp_path/'audit.csv').status.tolist()==['calendar_date_preserved']


def test_explicit_manual_correction_remains_highest_priority(tmp_path,monkeypatch):
    reports,_=fixture(tmp_path,monkeypatch,[('2026-10-23','MFN / calendar','2026-10-09')])
    manual=tmp_path/'manual.csv'
    pd.DataFrame([dict(ticker='EXAMPLE.ST',report_period='2026-Q3',report_date='2026-10-24',source='Verified issuer correction')]).to_csv(manual,index=False)
    assert apply_date_evidence(reports,auto_path=tmp_path/'none',manual_path=manual).effective_date.iloc[0]==pd.Timestamp('2026-10-24')


def test_future_quarter_and_unconfirmed_calendar_do_not_move_old_eps(tmp_path,monkeypatch):
    reports,resolve=fixture(tmp_path,monkeypatch,[('2027-02-01','MFN / calendar','2026-10-25')])
    assert resolve(reports).empty
    assert apply_date_evidence(reports,auto_path=tmp_path/'a',manual_path=tmp_path/'m').effective_date.equals(reports.effective_date)


def test_latest_official_calendar_revision_wins(tmp_path,monkeypatch):
    reports,resolve=fixture(tmp_path,monkeypatch,[('2026-10-22','MFN / calendar','2026-10-01'),
        ('2026-10-23','MFN / calendar','2026-10-09')])
    assert resolve(reports).report_date.tolist()==['2026-10-23']


def test_same_rank_conflict_is_not_silently_selected(tmp_path,monkeypatch):
    reports,resolve=fixture(tmp_path,monkeypatch,[('2026-10-22','MFN / calendar','2026-10-09'),
        ('2026-10-23','MFN / calendar','2026-10-09')])
    with pytest.raises(ValueError,match='Motstridiga rapportkalendrar'): resolve(reports)


def test_calendar_prevents_premature_eps_and_saved_canonical_date_is_correct(tmp_path,monkeypatch):
    reports,resolve=fixture(tmp_path,monkeypatch,[('2026-10-23','MFN / calendar','2026-10-09')])
    assert resolve(reports,today='2026-10-22').report_date.tolist()==['2026-10-23']
    import src.fundamentals as module
    path=tmp_path/'reports.csv'
    monkeypatch.setattr(module,'REPORTS_FILE',path)
    module.save_reports(reports,path)
    saved=pd.read_csv(path)
    assert saved.effective_date.tolist()==['2026-10-23']
    assert saved.eps_ttm.tolist()==[5.25]


def test_unconfirmed_calendar_range_is_not_publication_evidence(tmp_path,monkeypatch):
    reports,resolve=fixture(tmp_path,monkeypatch,[('2026-10-23','MFN / calendar','2026-10-09')])
    p=tmp_path/'calendar.csv';rows=pd.read_csv(p)
    rows['date_status']='estimated'; rows.to_csv(p,index=False)
    assert resolve(reports).empty
    rows['date_status']='confirmed';rows['report_date_end']='2026-10-24';rows.to_csv(p,index=False)
    assert resolve(reports).empty
