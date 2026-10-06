import numpy as np
import pytest

from src.method_metrics import equity_metrics, hold_curve


def test_sharpe_uses_daily_returns_sample_variance_and_252_not_total_return():
    changes = np.array([.01, -.02, .03, 0, .015])
    equity = np.cumprod(1 + changes)
    result = equity_metrics(equity)
    expected = changes.mean() / changes.std(ddof=1) * np.sqrt(252)
    assert result["sharpe_ratio"] == pytest.approx(expected)
    assert result["max_drawdown_pct"] == pytest.approx(-2)


@pytest.mark.parametrize("values", [[], [1], [1, 1, 1], [1.01, 1.0201, 1.030301]])
def test_no_observations_or_no_variation_has_no_sharpe(values):
    assert equity_metrics(np.asarray(values))["sharpe_ratio"] is None


def test_buy_and_hold_cash_dividends_commission_and_actual_period_bounds():
    candles = [{"date": "2026-01-01", "close": 10}, {"date": "2026-01-02", "close": 100},
               {"date": "2026-01-05", "close": 90}, {"date": "2026-01-06", "close": 120}]
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    dividends = [{"date": "2026-01-02", "amount": 50}, {"date": "2026-01-05", "amount": 5},
                 {"date": "2026-01-06", "amount": 2}, {"date": "2026-01-07", "amount": 99}]
    equity, trade = hold_curve(candles, dividends, dates)
    np.testing.assert_allclose(equity, [100/100.25, 95/100.25, (120*.9975+7)/100.25])
    assert trade["entry_date"] == "2026-01-02"
    assert trade["exit_date"] == "2026-01-06"
    assert trade["return_pct"] == pytest.approx((126.7/100.25-1)*100)


def test_index_has_no_fees_or_extra_dividends_and_initial_cash_counts_drawdown():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    equity, trade = hold_curve([{"date": d, "close": c} for d,c in zip(dates,[100,80,120])], [], dates, commission=0)
    assert trade["return_pct"] == pytest.approx(20)
    assert equity_metrics(equity)["max_drawdown_pct"] == pytest.approx(-20)
    assert equity_metrics(np.array([.99,.98]))["max_drawdown_pct"] == pytest.approx(-2)


def test_later_listing_stays_in_cash_until_first_available_quote():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    equity, trade = hold_curve([{"date": dates[2], "close": 100}, {"date": dates[3], "close": 110}], [], dates)
    assert list(equity[:2]) == [1,1]
    assert trade["entry_date"] == dates[2]


def test_fewer_than_two_quotes_preserves_cash_without_a_fake_trade():
    equity, trade = hold_curve([{"date": "2026-01-02", "close": 100}], [], ["2026-01-02", "2026-01-05"])
    assert list(equity) == [1,1]
    assert trade is None
