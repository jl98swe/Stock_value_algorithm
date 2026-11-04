"""Synthetic examples: announcements cannot manufacture earlier trades."""
import pandas as pd

from src.strategy import run_strategy
from src.strategy_backtests import report_filters, report_knowledge


def prices():
    dates = pd.bdate_range('2026-10-16', '2026-11-05')
    return pd.DataFrame(dict(Date=dates, Open=100., Close=100., Low=100., Score=0.,
                              MA200=90., FundamentalLock=False))


def test_new_calendar_does_not_create_old_october_buy():
    day = pd.Timestamp('2027-01-28')
    data = report_filters(prices(), [pd.Timestamp('2026-10-15'), day], {day: pd.Timestamp('2026-10-31')})
    assert not data.loc[data.Date.lt('2026-10-31'), 'BuyAllowed'].any()
    trades = run_strategy(data, 'EXAMPLE.ST')
    assert trades['open_lots'][0]['entry_signal_date'] == '2026-11-02'
    assert trades['open_lots'][0]['entry_date'] == '2026-11-03'


def test_next_opening_must_not_use_tomorrows_calendar_announcement():
    day = pd.Timestamp('2027-01-28')
    data = report_filters(prices(), [day], {day: pd.Timestamp('2026-11-03')})
    assert not data.loc[data.Date.eq('2026-11-02'), 'BuyAllowed'].iloc[0]
    assert data.loc[data.Date.eq('2026-11-03'), 'BuyAllowed'].iloc[0]
    assert run_strategy(data, 'EXAMPLE.ST')['open_lots'][0]['entry_date'] == '2026-11-04'


def test_report_cannot_force_sale_before_it_was_known():
    data = prices()
    day = pd.Timestamp('2026-11-05')
    filtered = report_filters(data, [day], {day: day})
    assert not filtered.ForceReportExit.any()


def test_first_observation_is_preserved_when_current_calendar_is_refreshed(monkeypatch):
    import src.strategy_backtests as module
    day = pd.Timestamp('2027-01-28')
    def observation(date):
        return pd.DataFrame([dict(ticker='EXAMPLE.ST', report_date_start=day,
                                   observed_date=pd.Timestamp(date))])
    monkeypatch.setattr(module, 'calendar_history', lambda: observation('2026-10-31'))
    monkeypatch.setattr(module, 'automatic_calendar', lambda: observation('2026-11-04'))
    monkeypatch.setattr(module, 'legacy_calendar_knowledge', lambda: pd.DataFrame(columns=['ticker','report_date','known_from']))
    assert report_knowledge('EXAMPLE.ST', [day]) == {day: pd.Timestamp('2026-10-31')}
    # The same rule survives once the scheduled date is a realised report.
    assert report_knowledge('EXAMPLE.ST', [day])[day] == pd.Timestamp('2026-10-31')


def test_missing_observation_does_not_invent_historical_permission(monkeypatch):
    import src.strategy_backtests as module
    monkeypatch.setattr(module, 'calendar_history', lambda: pd.DataFrame())
    monkeypatch.setattr(module, 'automatic_calendar', lambda: pd.DataFrame())
    monkeypatch.setattr(module, 'legacy_calendar_knowledge', lambda: pd.DataFrame(columns=['ticker','report_date','known_from']))
    day = pd.Timestamp('2027-01-28')
    assert report_knowledge('EXAMPLE.ST', [day]) == {day: day}
