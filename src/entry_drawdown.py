"""Entry-relative close loss; enrich saved exports without rerunning trading rules."""
from __future__ import annotations

import json
import math
from pathlib import Path


def entry_drawdown(candles: list[dict], trade: dict, end: str | None = None) -> float | None:
    price = trade.get('entry_price')
    first = trade.get('entry_date')
    last = trade.get('exit_date') or trade.get('valuation_date') or end
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0 or not first or not last:
        return None
    worst = 0.0
    for candle in candles:
        day, close = candle['date'], candle.get('close')
        # Strategy exits execute at the open or intraday (stop loss): that day's
        # close occurs after ownership ends. Benchmark exits use the closing price.
        if candle.get('preliminary') or not first <= day <= last:
            continue
        if trade.get('exit_date') == day and trade.get('exit_reason') != 'period_end':
            continue
        if isinstance(close, (int, float)) and math.isfinite(close) and close > 0:
            worst = min(worst, (close / price - 1) * 100)
    return worst


def enrich_aggregate(payload: dict, stocks: dict, index_candles: list[dict]) -> dict:
    def annotate(trade, end):
        candles = index_candles if trade.get('ticker') == 'OMXSGI' else stocks.get(trade.get('ticker'), {}).get('candles', [])
        trade['entry_drawdown_pct'] = entry_drawdown(candles, trade, end)
        return trade

    for key, variant in payload.items():
        if key in ('meta', 'periods'):
            continue
        for trade in variant.get('closed_trades', []) + variant.get('open_lots', []):
            annotate(trade, payload['meta']['end_date'])
    for period in payload.get('periods', {}).values():
        for key, trades in period.get('reference_trades', {}).items():
            for trade in trades:
                annotate(trade, period['end_date'])
        for key, summary in period.get('strategies', {}).items():
            trades = period.get('reference_trades', {}).get(key)
            if trades is None:
                trades = [t for t in payload[key]['closed_trades'] if period['start_date'] <= t['entry_date'] <= t['exit_date'] <= period['end_date']]
            values = [t['entry_drawdown_pct'] for t in trades if t.get('entry_drawdown_pct') is not None]
            summary['entry_drawdown_pct'] = min(values) if values else None
    return payload


def main():
    root = Path(__file__).resolve().parents[1] / 'docs' / 'data'
    target = root / 'backtests' / 'all.json'
    payload = json.loads(target.read_text())
    stocks = {p.stem: json.loads(p.read_text()) for p in (root / 'dashboard').glob('*.json') if p.stem != 'index'}
    index = json.loads((root / 'benchmarks' / 'omxsgi.json').read_text())
    enrich_aggregate(payload, stocks, index.get('candles', []))
    target.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(f"Entry drawdown exported for {payload['meta']['stock_count']} stocks; existing trades preserved.")


if __name__ == '__main__':
    main()
