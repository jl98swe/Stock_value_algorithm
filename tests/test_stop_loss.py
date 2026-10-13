"""Synthetic examples for protective stops and independent strategy positions."""
import pandas as pd
import pytest
from src.strategy import run_strategy


def example(opens, lows, scores=None):
    return pd.DataFrame({'Date': pd.bdate_range('2026-01-05', periods=len(opens)),
                         'Open': opens, 'Close': opens, 'Low': lows,
                         'Score': scores or [0] + [50] * (len(opens)-1)})


def test_intraday_touch_including_entry_day_and_net_commission():
    data = example([100, 100, 100], [100, 90, 100])
    result = run_strategy(data, 'EXAMPLE.ST', stop_loss_pct=10)
    trade = result['trades'][0]
    assert trade['entry_date'] == trade['exit_date'] == '2026-01-06'
    assert trade['exit_price'] == 90
    assert trade['exit_reason'] == 'stop_loss'
    assert trade['holding_trading_days'] == 0
    assert trade['return_pct'] == pytest.approx((90*.9975/(100*1.0025)-1)*100)
    assert not result['open_lots']
    assert len(run_strategy(data, 'EXAMPLE.ST')['open_lots']) == 1


def test_opening_gap_fills_at_open_and_overrides_eps_lock():
    data = example([100, 100, 85], [100, 95, 80])
    data['FundamentalLock'] = [False, False, True]
    result = run_strategy(data, 'EXAMPLE.ST', stop_loss_pct=10)
    assert result['trades'][0]['exit_price'] == 85
    assert result['signals'][-1]['exit_reason'] == 'stop_loss'
    assert result['state'].iloc[-1]['PositionLots'] == 0


def test_stop_is_fixed_to_entry_and_not_a_trailing_stop():
    result = run_strategy(example([100, 100, 120, 100], [100, 95, 115, 99]),
                          'EXAMPLE.ST', stop_loss_pct=10)
    assert not result['trades']
    assert len(result['open_lots']) == 1


def test_ordinary_score_sell_at_open_precedes_later_intraday_low():
    data = example([100, 100, 110], [100, 95, 80], [0, 100, 50])
    result = run_strategy(data, 'EXAMPLE.ST', stop_loss_pct=10)
    assert result['trades'][0]['exit_price'] == 110
    assert result['trades'][0]['exit_reason'] == 'score'
    assert len(result['trades']) == 1


def test_stop_ignores_sell_cooldown_and_nan_score_but_keeps_buy_rearm():
    data = example([100]*9, [100, 95, 90, 100, 100, 100, 100, 90, 100],
                   [0, 0, 0, 0, 0, 50, 0, float('nan'), 0])
    result = run_strategy(data, 'EXAMPLE.ST', stop_loss_pct=10)
    assert [t['entry_date'] for t in result['trades']] == ['2026-01-06', '2026-01-14']
    assert not result['open_lots']
    assert len([s for s in result['signals'] if s['side']=='BUY' and s['status']=='executed']) == 2


def test_missing_lows_are_not_silently_replaced_by_closes():
    with pytest.raises(ValueError, match='Low'):
        run_strategy(example([100,100], [100,100]).drop(columns='Low'), 'EXAMPLE.ST', stop_loss_pct=10)
