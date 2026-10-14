"""Synthetic examples for the independent two-position strategy."""
import pandas as pd
import pytest

from src.strategy import run_strategy
from src.aggregate_backtests import closed_equity
from src.pipeline import _position_payload


def run(scores, prices=None):
    prices = prices or [100.] * len(scores)
    frame = pd.DataFrame({'Date': pd.bdate_range('2026-01-05', periods=len(scores)),
        'Open': prices, 'Close': prices, 'Score': scores})
    return run_strategy(frame, 'EXAMPLE.ST', max_lots=2, buy_rearm_score=5, sell_rearm_score=95)


def executed(result, side):
    return [s for s in result['signals'] if s['side'] == side and s['status'] == 'executed']


def test_buy_requires_exact_five_or_higher_and_five_sessions():
    result = run([0, 4.999, 0, 0, 5, 0, 50])
    buys = executed(result, 'BUY')
    assert [s['signal_date'] for s in buys] == ['2026-01-05', '2026-01-12']
    assert result['state']['PositionLots'].max() == 2
    lots = result['open_lots']
    assert lots[0]['quantity'] * lots[0]['entry_price'] + lots[0]['entry_fee'] == pytest.approx(.5)
    assert result['state'].iloc[-1]['Cash'] + sum(lot['quantity'] * lot['entry_price'] + lot['entry_fee'] for lot in lots) == pytest.approx(1)
    assert _position_payload(result)['max_lots'] == 2
    assert _position_payload(result)['buy_rearm_score'] == 5


def test_small_rebound_never_rearms_second_buy():
    result = run([0, 4.999, 0, 0, 0, 0, 0, 0])
    assert len(executed(result, 'BUY')) == 1
    assert not result['state'].iloc[-1]['BuyArmed']


def test_rearmed_buy_waits_for_cooldown_without_another_rebound():
    result = run([0, 5, 0, 0, 0, 0, 50])
    assert len(executed(result, 'BUY')) == 2
    assert executed(result, 'BUY')[1]['signal_date'] == '2026-01-12'


def test_sales_require_ninety_five_and_sell_separate_fifo_lots():
    result = run([0, 5, 50, 50, 50, 0, 100, 95.001, 100, 100, 95, 100, 50])
    sells = executed(result, 'SELL')
    assert [s['signal_date'] for s in sells] == ['2026-01-13', '2026-01-20']
    assert [s['lot_id'] for s in sells] == [s['lot_id'] for s in executed(result, 'BUY')]
    assert len(result['trades']) == 2
    assert not result['open_lots']


def test_capacity_can_be_refilled_after_partial_sale():
    result = run([0, 5, 50, 50, 50, 0, 100, 50, 0, 0, 0, 50])
    assert len(executed(result, 'BUY')) == 3
    assert len(result['open_lots']) == 2
    assert result['state']['PositionLots'].max() == 2


def test_shared_closed_capital_matches_net_cash_replay():
    prices = [100, 100, 100, 100, 100, 100, 100, 110, 110, 110, 110, 110, 120]
    scores = [0, 5, 50, 50, 50, 0, 100, 95, 100, 100, 100, 100, 50]
    result = run(scores, prices)
    dates = pd.bdate_range('2026-01-05', periods=len(scores)).strftime('%Y-%m-%d').tolist()
    candles = [{'date': d, 'close': p} for d, p in zip(dates, prices)]
    equity = closed_equity(candles, result['trades'], [], dates, max_lots=2)
    assert equity == pytest.approx(result['state']['Equity'].to_numpy())
    assert equity[-1] < (1 + result['trades'][0]['return_pct']/100) * (1 + result['trades'][1]['return_pct']/100)
