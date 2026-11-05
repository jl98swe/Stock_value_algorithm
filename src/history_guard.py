"""Independent publication gate against the committed, previously published history."""
from __future__ import annotations

from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from .config import ROOT
from .strategy_overviews import STRATEGIES

CORRECTIONS = Path('data/manual/history_corrections.json')
SNAPSHOT = 'data/derived/report_score_dates.csv'
HISTORY = 'data/derived/valuation_score_history.csv.gz'


def publication_cutoffs(old: pd.DataFrame, new: pd.DataFrame) -> dict[str, str]:
    """Derive allowed dates independently of the pipeline's invalidation code.

    Model/quarter-end dates must NEVER grant permission to rewrite history.
    """
    fields = ['effective_date', 'eps_ttm', 'eps_currency', 'verified']
    def rows(frame):
        return {(str(r['ticker']), str(r['report_period'])): r for r in frame.to_dict('records')}
    before, after = rows(old), rows(new)
    cutoffs = {}
    for key in before.keys() | after.keys():
        a, b = before.get(key, {}), after.get(key, {})
        def value(row, field):
            v = row.get(field)
            if pd.isna(v) or v == '':
                return None
            if field == 'effective_date':
                return pd.Timestamp(v).date().isoformat()
            if field == 'verified':
                return str(v).lower() in ('true', '1')
            return str(v)
        if all(value(a, f) == value(b, f) for f in fields):
            continue
        days = [value(r, 'effective_date') for r in (a, b)
                if value(r, 'verified') and value(r, 'effective_date') and value(r, 'eps_ttm')]
        if days:
            day = min(days)
            cutoffs[key[0]] = min(day, cutoffs.get(key[0], day))
    return cutoffs


def assert_score_history(old: pd.DataFrame, new: pd.DataFrame, cutoffs: dict[str, str]) -> None:
    def prepared(frame):
        result = frame[['ticker', 'date', 'score']].copy()
        result['date'] = pd.to_datetime(result.date).dt.strftime('%Y-%m-%d')
        if result.duplicated(['ticker', 'date']).any():
            raise ValueError('Historikskydd: dubbla ticker+date')
        return result
    a, b = prepared(old), prepared(new)
    last_dates = a.groupby('ticker').date.max()
    merged = a.merge(b, on=['ticker', 'date'], how='outer', suffixes=('_old', '_new'), indicator=True)
    protected = (merged.date.lt(merged.ticker.map(cutoffs).fillna('9999-12-31'))
                 & merged.date.le(merged.ticker.map(last_dates).fillna('')))
    changed = merged['_merge'].ne('both') | ~np.isclose(
        merged.score_old, merged.score_new, rtol=0, atol=1e-10, equal_nan=True)
    bad = merged.loc[protected & changed, ['ticker', 'date']]
    if not bad.empty:
        raise ValueError('Historikskydd: publicerad poäng ändrad/tillagd/borttagen: '
                         + str(bad.head(5).to_dict('records')))


def approved_report_exits(records: list) -> Counter:
    """Explicit, addition-only execution repairs never grant score cutoffs."""
    result = Counter()
    for record in records:
        for repair in record.get('report_exit_additions', []):
            if not str(record.get('reason', '')).strip() or not str(repair.get('source', '')).strip():
                raise ValueError('Historikskydd: rapportaffärsrättelse kräver orsak och källa')
            report = pd.Timestamp(repair['report_date']).normalize()
            day = pd.Timestamp(repair['execution_date']).normalize()
            known = pd.Timestamp(repair['known_from']).normalize()
            import exchange_calendars as xcals
            calendar = xcals.get_calendar('XSTO', start=report - pd.Timedelta(days=15),
                                          end=report + pd.Timedelta(days=1))
            sessions = calendar.sessions.tz_localize(None)
            prior_session = sessions[sessions.searchsorted(report, side='left') - 1]
            if day != prior_session or known > day:
                raise ValueError('Historikskydd: rapportförsäljning kräver föregående handelsdag och tidigare kalenderkunskap')
            event = json.dumps([repair['ticker'], 'exit', day.date().isoformat(),
                                day.date().isoformat(), round(float(repair['price']), 8),
                                repair['lot_id']], ensure_ascii=False)
            result[event] += 1
    return result


def assert_trade_history(old: dict, new: dict, cutoffs: dict[str, str],
                         report_exit_additions: Counter | None = None) -> None:
    """Compare executions, including entries that move from open to closed lots.

    Exclude returns/drawdown that legitimately evolve as more prices arrive.
    """
    for strategy in STRATEGIES:
        previous = old.get(strategy, {})
        current = new.get(strategy, {})
        rows = previous.get('closed_trades', []) + previous.get('open_lots', [])
        last = max([old.get('meta', {}).get('end_date', '')] +
                   [str(r.get(f) or '') for r in rows for f in ('entry_date', 'exit_date')])
        def executions(payload):
            events = []
            for r in payload.get('closed_trades', []) + payload.get('open_lots', []):
                ticker = r['ticker']
                for prefix in ('entry', 'exit'):
                    day = r.get(prefix + '_date')
                    if not day or day > last or day >= cutoffs.get(ticker, '9999-12-31'):
                        continue
                    events.append(json.dumps([ticker, prefix, r.get(prefix + '_signal_date'), day,
                                              round(float(r[prefix + '_price']), 8), r.get('lot_id')],
                                             ensure_ascii=False))
            return Counter(events)
        a, b = executions(previous), executions(current)
        if strategy == 'report_avoidance' and report_exit_additions:
            # Only add the audited report exit of an existing published lot.
            # Changed entries, prices, dates, other strategies and removals
            # remain protected, even after this repair has been published.
            open_ids = {(r['ticker'], r.get('lot_id')) for r in previous.get('open_lots', [])}
            eligible = Counter()
            for r in current.get('closed_trades', []):
                if r.get('exit_reason') != 'report' or (r['ticker'], r.get('lot_id')) not in open_ids:
                    continue
                event = json.dumps([r['ticker'], 'exit', r.get('exit_signal_date'), r.get('exit_date'),
                                    round(float(r['exit_price']), 8), r.get('lot_id')], ensure_ascii=False)
                eligible[event] += 1
            allowed = (b - a) & report_exit_additions & eligible
            b -= allowed
        if a != b:
            changes = list((a - b).elements()) + list((b - a).elements())
            raise ValueError(f'Historikskydd: publicerad affär ändrad i {strategy}: {changes[:3]}')


def correction_cutoffs(records: list, base_commit: str) -> dict[str, str]:
    result = {}
    for record in records:
        if record.get('base_commit') != base_commit:
            continue
        if not str(record.get('reason', '')).strip():
            raise ValueError('Historikskydd: avsiktlig rättelse kräver en dokumenterad orsak')
        for ticker, day in record['from'].items():
            parsed = pd.Timestamp(day).date().isoformat()
            result[ticker] = min(parsed, result.get(ticker, parsed))
    return result


def validate_history(*, root: Path = ROOT, base_ref: str = 'HEAD') -> None:
    """Fail closed before publishing, even if the build overwrote its snapshot."""
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)
    base = git('rev-parse', base_ref).decode().strip()
    def prior(path):
        return git('show', f'{base}:{path}')
    old_snapshot = pd.read_csv(BytesIO(prior(SNAPSHOT)))
    current_snapshot = pd.read_csv(root / SNAPSHOT)
    cutoffs = publication_cutoffs(old_snapshot, current_snapshot)
    records = json.loads((root / CORRECTIONS).read_text()) if (root / CORRECTIONS).exists() else []
    for ticker, day in correction_cutoffs(records, base).items():
        cutoffs[ticker] = min(day, cutoffs.get(ticker, day))
    old_history = pd.read_csv(BytesIO(prior(HISTORY)), compression='gzip', float_precision='round_trip')
    new_history = pd.read_csv(root / HISTORY, float_precision='round_trip')
    assert_score_history(old_history, new_history, cutoffs)
    # Also compare exported (rounded) scores so corrupt JSON cannot pass merely
    # because the frozen CSV is intact. Split JSON consistency is checked by
    # validate_outputs as well.
    old_dashboard = json.loads(prior('docs/data/dashboard.json'))
    new_dashboard = json.loads((root / 'docs/data/dashboard.json').read_text())
    def exported(payload):
        return pd.DataFrame([dict(ticker=t, date=r['date'], score=r['value'])
                             for t, s in payload['stocks'].items() for r in s.get('scores', [])],
                            columns=['ticker', 'date', 'score'])
    assert_score_history(exported(old_dashboard), exported(new_dashboard), cutoffs)
    assert_trade_history(json.loads(prior('docs/data/backtests/all.json')),
                         json.loads((root / 'docs/data/backtests/all.json').read_text()), cutoffs,
                         approved_report_exits(records))
    print(f'Historikskydd OK mot {base[:12]}: publicerade poäng och affärer bevarade före tillåtna datum.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Stoppa publicering som skriver om skyddad historik.')
    parser.add_argument('--base-ref', default='HEAD')
    args = parser.parse_args()
    validate_history(base_ref=args.base_ref)
