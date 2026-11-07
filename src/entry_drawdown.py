"""Entry-relative close loss; enrich saved exports without rerunning trading rules."""
from __future__ import annotations

import json
import math
from pathlib import Path


def entry_drawdown_metrics(candles: list[dict], trade: dict, end: str | None = None) -> dict:
    price = trade.get('entry_price')
    first = trade.get('entry_date')
    last = trade.get('exit_date') or trade.get('valuation_date') or end
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0 or not first or not last:
        return {'entry_drawdown_pct': None, 'entry_drawdown_days': None}
    lowest, days, session = math.inf, None, 0
    for candle in sorted(candles, key=lambda c: c['date']):
        day, close = candle['date'], candle.get('close')
        # Opening/intraday exits exclude that day's close; benchmarks exit at close.
        if candle.get('preliminary') or not first <= day <= last:
            continue
        if trade.get('exit_date') == day and trade.get('exit_reason') != 'period_end':
            continue
        if day > first:
            session += 1
        if isinstance(close, (int, float)) and math.isfinite(close) and 0 < close <= lowest:
            lowest, days = close, session
    return {'entry_drawdown_pct': min(0.0, (lowest / price - 1) * 100) if math.isfinite(lowest) else 0.0,
            'entry_drawdown_days': days}


def entry_upside_metrics(candles: list[dict], trade: dict, end: str | None = None) -> dict:
    price, first = trade.get('entry_price'), trade.get('entry_date')
    last = trade.get('exit_date') or trade.get('valuation_date') or end
    empty = {'entry_upside_pct': None, 'entry_upside_days': None}
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0 or not first or not last:
        return empty
    highest, peak_session, session = -math.inf, None, 0
    for candle in sorted(candles, key=lambda c: c['date']):
        day, close = candle['date'], candle.get('close')
        if candle.get('preliminary') or not first <= day <= last:
            continue
        if day > first:
            session += 1
        if trade.get('exit_date') == day and trade.get('exit_reason') != 'period_end':
            continue
        if isinstance(close, (int, float)) and math.isfinite(close) and close > 0 and close >= highest:
            highest, peak_session = close, session
    if peak_session is None:
        return empty
    return {'entry_upside_pct': (highest / price - 1) * 100,
            'entry_upside_days': session - peak_session if trade.get('exit_date') and not trade.get('open') else None}


def entry_drawdown(candles: list[dict], trade: dict, end: str | None = None) -> float | None:
    return entry_drawdown_metrics(candles, trade, end)['entry_drawdown_pct']


def enrich_aggregate(payload: dict, stocks: dict, index_candles: list[dict]) -> dict:
    def annotate(trade, end):
        candles = index_candles if trade.get('ticker') == 'OMXSGI' else stocks.get(trade.get('ticker'), {}).get('candles', [])
        trade.update(entry_drawdown_metrics(candles, trade, end))
        trade.update(entry_upside_metrics(candles, trade, end))
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
            values = [t for t in trades if t.get('entry_drawdown_pct') is not None]
            worst = min(values, key=lambda t: t['entry_drawdown_pct']) if values else {}
            summary['entry_drawdown_pct'] = worst.get('entry_drawdown_pct')
            summary['entry_drawdown_days'] = worst.get('entry_drawdown_days')
            gains = [t for t in trades if t.get('entry_upside_pct') is not None]
            best = max(gains, key=lambda t: t['entry_upside_pct']) if gains else {}
            summary['entry_upside_pct'] = best.get('entry_upside_pct')
            summary['entry_upside_days'] = best.get('entry_upside_days')
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
