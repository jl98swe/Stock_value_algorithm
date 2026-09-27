import pandas as pd

from src.pipeline import _strategy_comparison


def test_buy_and_hold_uses_same_dates_and_dividends_without_future_payments():
    days = pd.date_range('2026-01-01', periods=4)
    frame = pd.DataFrame({'date': days, 'close': [100, 110, 90, 120]})
    dividends = pd.DataFrame({'ticker': ['T.ST'] * 3, 'ex_date': [days[0], days[2], days[3]], 'dividend': [4, 5, 2]})
    strategy = {'state': pd.DataFrame({'Date': days[:3]}), 'summary': {
        'total_return_pct': 3, 'max_drawdown_pct': -4, 'closed_lots': 1, 'win_rate_pct': 100}}

    strategy_row, stock_row = _strategy_comparison(strategy, frame, dividends, 'T.ST')

    assert strategy_row['start_date'] == '2026-01-01'
    assert stock_row['end_date'] == '2026-01-03'
    assert stock_row['return_pct'] == -5
    assert stock_row['max_drawdown_pct'] == -13.64
    assert stock_row['trades'] is None
