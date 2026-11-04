"""Audited recovery of all five additional EPS cases and calendar repainting."""
from io import BytesIO
import json
import subprocess

import pandas as pd

from .config import ROOT
from .history_guard import CORRECTIONS, HISTORY
from .score_history import load_score_history, save_score_history, normalise_score_history

CORRECTION_ID = 'restore-additional-audit-cases-2026-11-04'
CASES = {
    'ABB.ST': ('56c7b0848524166753112b4de1b13bb444ef57dc', '2026-10-20'),
    'EAST.ST': ('56c7b0848524166753112b4de1b13bb444ef57dc', '2026-10-22'),
    'AZN.ST': ('1b387cdab94aee6dd6c2647566d5856ceb210185', '2026-10-30'),
    'REJL-B.ST': ('1b387cdab94aee6dd6c2647566d5856ceb210185', '2026-11-03'),
    'FOI-B.ST': ('33b58c59141b7473333ee14d96b33f24d510a31d', '2026-11-05'),
}


def restore() -> None:
    audit = ROOT / CORRECTIONS
    records = json.loads(audit.read_text()) if audit.exists() else []
    if any(r.get('correction_id') == CORRECTION_ID for r in records):
        print('De ytterligare granskningsfallen är redan återställda.')
        return
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args])
    history = load_score_history()
    # Never restore reports.csv from an older commit: verified manual values,
    # source data and the actual publication dates must survive this repair.
    cache = {}
    repairs = []
    for ticker, (source, cutoff) in CASES.items():
        if source not in cache:
            original = pd.read_csv(BytesIO(git('show', f'{source}:{HISTORY}')),
                                   compression='gzip', float_precision='round_trip')
            cache[source] = normalise_score_history(original)
        original = cache[source]
        def affected(frame):
            return frame.ticker.eq(ticker) & frame.date.ge('2026-09-30') & frame.date.lt(cutoff)
        old = original.loc[affected(original)].copy()
        current = history.loc[affected(history)].copy()
        if old.empty or not set(old.date).issubset(set(current.date)):
            raise ValueError(f'Referensdatum stämmer inte för {ticker}')
        missing_days = sorted(set(current.date) - set(old.date))
        # Later sessions may also have inherited the unpublished EPS. Compute
        # only those missing reference dates with the reports known that day.
        if missing_days:
            from .fetch_data import load_price_history
            from .fundamentals import load_reports, valuation_calculation_mode
            from .eps_conversion import apply_fx_fallbacks
            from .pipeline import _valuation_input
            from .model_data import ensure_gbm_model
            from .valuation import GBMModel, calculate_valuation
            prices = load_price_history()
            reports = apply_fx_fallbacks(load_reports())
            model = GBMModel.load(ensure_gbm_model())
            additions = []
            for day in missing_days:
                available = reports.loc[reports.effective_date.le(day)]
                mode = valuation_calculation_mode(ticker, available)
                frame = prices.loc[prices.ticker.eq(ticker) & prices.date.le(day)].copy()
                valued = calculate_valuation(_valuation_input(frame, ticker, available, mode), model=model)
                score = float(valued.loc[valued.Date.eq(day), 'Score'].iloc[0])
                additions.append(dict(ticker=ticker, date=day, score=score,
                                      calculation_mode=mode, frozen_at=pd.Timestamp.now(tz='Europe/Stockholm').isoformat()))
            old = pd.concat([old, normalise_score_history(pd.DataFrame(additions))], ignore_index=True)
        repairs.append(dict(ticker=ticker, source_commit=source, before=cutoff,
                            restored_dates=len(old), newly_recomputed_dates=len(missing_days)))
        history = pd.concat([history.loc[~affected(history)], old], ignore_index=True)
    permits = {t: '2026-09-30' for t in CASES}
    permits.update({'AZN.ST': '2026-08-03', 'ALLEI.ST': '2026-10-27',
                    'EPI-A.ST': '2026-10-29', 'NDA-SE.ST': '2026-10-16', 'SEB-A.ST': '2026-10-23'})
    record = dict(correction_id=CORRECTION_ID, base_commit=git('rev-parse', 'HEAD').decode().strip(),
                  reason='Återställ samtliga ytterligare EPS-fall från granskningen av 119 aktier. '
                         'Rätta även kalenderberoende retroaktiva köp med arkiverad observationstid. '
                         'Verifierade EPS-värden och marknadsdata bevaras.', repairs=repairs,
                  **{'from': permits})
    save_score_history(history)
    audit.write_text(json.dumps(records + [record], ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    restore()
