"""Synthetic examples reproducing the Cloetta failure and the independent gate."""
from copy import deepcopy

import pandas as pd
import pytest

from src.fundamentals import normalise_reports
from src.history_guard import (assert_score_history, assert_trade_history,
                               correction_cutoffs, publication_cutoffs, validate_history)
from src.report_date_revisions import changed_eps_cutoffs, score_snapshot
from src.score_history import apply_frozen_scores
from src.strategy import run_strategy


def snapshots():
    reports = normalise_reports(pd.DataFrame([
        dict(ticker='EXAMPLE.ST', report_period='2026-Q2', period_end='2026-06-30',
             effective_date='2026-07-15', eps_ttm=2.9822,
             source='TradingView / diluted TTM', verified=True),
        dict(ticker='EXAMPLE.ST', report_period='2026-Q3', period_end='2026-09-30',
             effective_date='2026-11-04', eps_ttm=3.1822,
             source='Synthetic report', verified=True),
    ]))
    return reports, score_snapshot(reports.iloc[:1])


def test_cloetta_pattern_new_report_must_not_move_pre_report_sell():
    reports, previous = snapshots()
    cutoffs = changed_eps_cutoffs(reports, previous)
    assert cutoffs == {'EXAMPLE.ST': pd.Timestamp('2026-11-04')}
    dates = pd.to_datetime(['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22',
                            '2026-11-02', '2026-11-03', '2026-11-04'])
    history = pd.DataFrame(dict(ticker='EXAMPLE.ST', date=dates, score=[.5, 50, 99.54, 99.09, 99.999, 99.9, 99]))
    # New EPS changes the model's period-end state, including October values.
    candidate = pd.DataFrame(dict(Date=dates, Open=60., Close=60.,
                                  Score=[50, 50, 73.26, 77.03, 99.63, 96.71, 70],
                                  FundamentalLock=False, LockReason=''))
    corrected, _ = apply_frozen_scores(candidate, 'EXAMPLE.ST', history,
                                      frozen_at='synthetic', recalculate_from=cutoffs['EXAMPLE.ST'])
    assert corrected.Score.tolist() == [.5, 50, 99.54, 99.09, 99.999, 99.9, 70]
    trades = run_strategy(corrected, 'EXAMPLE.ST')['trades']
    assert trades[-1]['exit_signal_date'] == '2026-10-21'
    assert trades[-1]['exit_date'] == '2026-10-22'
    assert publication_cutoffs(previous, score_snapshot(reports)) == {'EXAMPLE.ST': '2026-11-04'}


def test_guard_blocks_the_original_bug_even_if_pipeline_cutoff_regresses():
    reports, previous = snapshots()
    cutoffs = publication_cutoffs(previous, score_snapshot(reports))
    old = pd.DataFrame([dict(ticker='EXAMPLE.ST', date='2026-10-21', score=99.54)])
    bad = old.assign(score=73.26)
    with pytest.raises(ValueError, match='publicerad poäng'):
        assert_score_history(old, bad, cutoffs)
    with pytest.raises(ValueError, match='publicerad poäng'):
        assert_score_history(old, old.iloc[:0], cutoffs)
    extra = pd.concat([old, old.assign(date='2026-10-20')])
    with pytest.raises(ValueError, match='publicerad poäng'):
        assert_score_history(old, extra, cutoffs)


def test_report_day_changes_and_new_sessions_are_allowed_but_other_tickers_are_protected():
    old = pd.DataFrame([dict(ticker='EXAMPLE.ST', date='2026-11-04', score=99.)])
    assert_score_history(old, old.assign(score=70), {'EXAMPLE.ST': '2026-11-04'})
    assert_score_history(old, pd.concat([old, old.assign(date='2026-11-05')]), {})
    with pytest.raises(ValueError):
        assert_score_history(old, old.assign(score=70), {'OTHER.ST': '2026-11-04'})


def test_trade_gate_checks_all_strategies_and_allows_pending_execution_and_lot_closure():
    trade = dict(ticker='EXAMPLE.ST', lot_id='lot-1', entry_signal_date='2026-10-19',
                 entry_date='2026-10-20', entry_price=60.)
    old = {'meta': {'end_date': '2026-10-21'}, 'ma200': {'open_lots': [trade]}}
    new = deepcopy(old)
    new['ma200'] = {'closed_trades': [{**trade, 'exit_date': '2026-10-22',
                                     'exit_signal_date': '2026-10-21', 'exit_price': 61.}]}
    assert_trade_history(old, new, {})
    new['ma200']['closed_trades'][0]['entry_date'] = '2026-10-21'
    with pytest.raises(ValueError, match='publicerad affär.*ma200'):
        assert_trade_history(old, new, {})


def test_correction_requires_reason_and_is_bound_to_one_base_commit():
    records = [{'base_commit': 'abc', 'reason': 'Synthetic verified historical repair',
                'from': {'EXAMPLE.ST': '2026-09-30'}}]
    assert correction_cutoffs(records, 'abc') == {'EXAMPLE.ST': '2026-09-30'}
    assert correction_cutoffs(records, 'next-commit') == {}
    records[0]['reason'] = ' '
    with pytest.raises(ValueError, match='orsak'):
        correction_cutoffs(records, 'abc')


def test_publication_gate_fails_closed_without_git_baseline(tmp_path):
    with pytest.raises(Exception):
        validate_history(root=tmp_path)


@pytest.mark.parametrize('corrupt_export', [False, True])
def test_gate_uses_git_baseline_after_local_snapshot_has_been_overwritten(tmp_path, corrupt_export):
    import json
    import subprocess
    from pathlib import Path
    def save(path, value):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, pd.DataFrame):
            value.to_csv(target, index=False)
        else:
            target.write_text(json.dumps(value))
    reports, previous = snapshots()
    history = pd.DataFrame([dict(ticker='EXAMPLE.ST', date='2026-10-21', score=99.54)])
    dashboard = {'stocks': {'EXAMPLE.ST': {'scores': [{'date': '2026-10-21', 'value': 99.54}]}}}
    save('data/derived/report_score_dates.csv', previous)
    save('data/derived/valuation_score_history.csv.gz', history)
    save('docs/data/dashboard.json', dashboard)
    save('docs/data/backtests/all.json', {'meta': {'end_date': '2026-11-03'}})
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'Synthetic published reference'], check=True)
    # The build overwrote its local report snapshot. Permission must still
    # come from publication date, not the new snapshot's model date (Sep 30).
    save('data/derived/report_score_dates.csv', score_snapshot(reports))
    if corrupt_export:
        dashboard['stocks']['EXAMPLE.ST']['scores'][0]['value'] = 73.26
        save('docs/data/dashboard.json', dashboard)
    else:
        save('data/derived/valuation_score_history.csv.gz', history.assign(score=73.26))
    with pytest.raises(ValueError, match='publicerad poäng'):
        validate_history(root=tmp_path)


def test_first_tradingview_report_cannot_reopen_older_publication_dates():
    reports, _ = snapshots()
    reports.loc[0, 'source'] = 'Synthetic official report'
    reports.loc[1, 'source'] = 'TradingView / diluted TTM'
    previous = score_snapshot(reports.iloc[:1])
    current = score_snapshot(reports)
    assert previous.calculation_mode.iloc[0] != current.calculation_mode.iloc[0]
    assert changed_eps_cutoffs(reports, previous) == {'EXAMPLE.ST': pd.Timestamp('2026-11-04')}
    assert publication_cutoffs(previous, current) == {'EXAMPLE.ST': '2026-11-04'}
