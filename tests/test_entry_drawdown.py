"""Synthetic examples of entry-price drawdown and export consistency."""
import pytest
from src.entry_drawdown import entry_drawdown, enrich_aggregate


def test_closes_during_ownership_only():
    candles = [{'date': f'2026-10-{20+i}', 'close': c} for i,c in enumerate([100, 120, 95, 50])]
    trade = {'entry_date': '2026-10-20', 'exit_date': '2026-10-23', 'entry_price': 100}
    assert entry_drawdown(candles, trade) == pytest.approx(-5)
    assert entry_drawdown(candles, dict(trade, exit_reason='period_end')) == -50
    assert entry_drawdown(candles[:2], trade) == 0
    assert entry_drawdown(candles, dict(trade, entry_price=None)) is None
    assert entry_drawdown([dict(candles[-1], preliminary=True)], trade) == 0


def test_enrichment_preserves_trades_and_summary_uses_worst_entry_loss():
    trade = {'ticker': 'EXAMPLE', 'entry_date': '2026-10-20', 'exit_date': '2026-10-23', 'entry_price': 100, 'return_pct': 10}
    data = {'meta': {'end_date':'2026-10-23'}, 'standard': {'closed_trades':[trade], 'open_lots':[]},
            'periods': {'all': {'start_date':'2026-10-20', 'end_date':'2026-10-23', 'strategies':{'standard':{'return_pct':10}}, 'reference_trades':{}}}}
    stocks = {'EXAMPLE': {'candles':[{'date':'2026-10-21','close':95}]}}
    result = enrich_aggregate(data, stocks, [])
    assert result['standard']['closed_trades'][0]['return_pct'] == 10
    assert result['periods']['all']['strategies']['standard']['entry_drawdown_pct'] == pytest.approx(-5)
    assert result['periods']['all']['strategies']['standard']['return_pct'] == 10
