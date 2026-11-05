"""Apply the audited LUMI correction and record its impact against a git baseline."""
from __future__ import annotations
import argparse
import csv
from io import BytesIO, StringIO
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from .config import ROOT
from .report_publications import PUBLICATIONS, publication_session

TICKER = 'LUMI.ST'
PREFIX = ROOT / 'reference/lumi_publication_2026-11-05'


def apply_inputs():
    """Change timing only, retaining every original EPS string and source."""
    with PUBLICATIONS.open() as handle:
        evidence = {r['report_period']: r for r in csv.DictReader(handle)}
    path = ROOT / 'data/fundamentals/reports.csv'
    with path.open() as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames)
        rows = list(reader)
    for column in ('report_date', 'publication_time_verified'):
        if column not in columns:
            columns.append(column)
    for row in rows:
        if row['ticker'] != TICKER:
            continue
        ev = evidence[row['report_period']]
        row.update(report_date=ev['report_date'], published_at=ev['published_at'],
                   publication_time_verified='True', effective_date=publication_session(
                       ev['published_at'], ev['report_date'])[0].date().isoformat())
        row['notes'] = row['notes'].replace('effective_date=report_date', 'effective_date=verified_publication_session').replace('effective_date=missing', 'effective_date=verified_publication_session').replace('existing same-day rule used.', 'verified publication session used.')
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    path = ROOT / 'data/fundamentals/eps_report_date_cache.csv'
    with path.open() as handle:
        reader = csv.DictReader(handle); columns = reader.fieldnames; rows = list(reader)
    rows = [r for r in rows if r['ticker'] != TICKER] + [
        dict(ticker=TICKER, report_period=k, report_date=v['report_date']) for k, v in evidence.items()]
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def impact(base_ref: str):
    def old(path):
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{base_ref}:{path}'])
    # The input correction must never change EPS amounts, source priority or market data.
    path = 'data/fundamentals/reports.csv'
    before = pd.read_csv(BytesIO(old(path)), dtype=str, keep_default_na=False).set_index(['ticker', 'report_period'])
    after = pd.read_csv(ROOT / path, dtype=str, keep_default_na=False).set_index(['ticker', 'report_period'])
    assert before.index.equals(after.index)
    assert before.eps_ttm.equals(after.eps_ttm), 'EPS amounts changed'
    assert before.source.equals(after.source), 'EPS sources changed'
    pd.testing.assert_frame_equal(before.loc[before.index.get_level_values(0) != TICKER],
        after.loc[after.index.get_level_values(0) != TICKER, before.columns])
    changed_paths = subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--name-only', base_ref]).decode().splitlines()
    assert not any(p.startswith(('data/prices/', 'data/raw/')) for p in changed_paths), 'Market inputs changed'
    path = 'data/derived/valuation_score_history.csv.gz'
    a = pd.read_csv(BytesIO(old(path)), compression='gzip', float_precision='round_trip')
    b = pd.read_csv(ROOT / path, float_precision='round_trip')
    merged = a.merge(b, on=['ticker', 'date'], how='outer', suffixes=('_before', '_after'), indicator=True)
    different = merged['_merge'].ne('both') | ~np.isclose(merged.score_before, merged.score_after, atol=1e-10, rtol=0, equal_nan=True)
    changes = merged.loc[different, ['ticker', 'date', 'score_before', 'score_after']]
    assert changes.ticker.eq(TICKER).all(), 'Other ticker score history changed'
    changes.to_csv(str(PREFIX) + '_score_changes.csv', index=False)
    old_dashboard = json.loads(old('docs/data/dashboard.json'))['stocks']
    new_dashboard = json.loads((ROOT / 'docs/data/dashboard.json').read_text())['stocks']
    for ticker, stock in old_dashboard.items():
        assert stock['candles'] == new_dashboard[ticker]['candles'], f'Candles changed: {ticker}'
        if ticker != TICKER:
            for field in ('scores', 'signals', 'closed_trades', 'open_lots', 'strategies'):
                assert stock[field] == new_dashboard[ticker][field], f'{field} changed: {ticker}'
    a, b = old_dashboard[TICKER], new_dashboard[TICKER]
    signal_changes = []
    for strategy in b['strategies']:
        def signals(stock):
            return {(r.get('signal_date', r.get('date')), r['side'], r.get('status')):r
                    for r in stock['strategies'][strategy].get('signals', [])}
        previous, current = signals(a), signals(b)
        for key in sorted(previous.keys() | current.keys(), key=str):
            x, y = previous.get(key), current.get(key)
            if x != y:
                signal_changes.append(dict(strategy=strategy, date=key[0], side=key[1], status=key[2], before=x, after=y))
    Path(str(PREFIX) + '_signal_changes.json').write_text(json.dumps(signal_changes, ensure_ascii=False, indent=2)+'\n')
    old_backtests = json.loads(old('docs/data/backtests/LUMI.ST.json'))
    new_backtests = json.loads((ROOT / 'docs/data/backtests/LUMI.ST.json').read_text())
    backtests = {}
    for name in old_backtests:
        if name.startswith('_'): continue
        x, y = old_backtests[name], new_backtests[name]
        backtests[name] = {'closed_trades_before':len(x.get('closed_trades', [])),
                          'closed_trades_after':len(y.get('closed_trades', [])),
                          'open_lots_before':len(x.get('open_lots', [])),
                          'open_lots_after':len(y.get('open_lots', [])),
                          'overview_before':x.get('overview'), 'overview_after':y.get('overview')}
    summary = dict(base_ref=base_ref, checked_reports=33, changed_score_rows=len(changes),
        newly_available_scores=int(changes.score_before.isna().sum()),
        first_changed_date=changes.date.min() if not changes.empty else None,
        last_changed_date=changes.date.max() if not changes.empty else None,
        changed_signal_records=len(signal_changes), other_118_histories_unchanged=True,
        prices_and_eps_amounts_unchanged=True,
        standard_comparison_before=a['strategy_comparison'], standard_comparison_after=b['strategy_comparison'],
        backtests=backtests)
    Path(str(PREFIX) + '_impact.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('backtests',)},ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--base-ref')
    args = parser.parse_args()
    if args.apply: apply_inputs()
    if args.base_ref: impact(args.base_ref)


if __name__ == '__main__': main()
