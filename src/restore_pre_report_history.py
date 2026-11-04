"""One-time, audited recovery of the five histories overwritten on 4 Nov 2026."""
from io import BytesIO
import json
import subprocess

import pandas as pd

from .config import ROOT
from .history_guard import CORRECTIONS, HISTORY
from .score_history import load_score_history, save_score_history

SOURCE = '6b69657027c54546ebf2576bd393e78eb4616103'
CORRECTION_ID = 'restore-pre-publication-history-2026-11-04'
TICKERS = ['CLA-B.ST', 'SINT.ST', 'CIBUS.ST', 'KAMBI.ST', 'MCOV-B.ST']


def restore() -> None:
    audit = ROOT / CORRECTIONS
    records = json.loads(audit.read_text()) if audit.exists() else []
    if any(r.get('correction_id') == CORRECTION_ID for r in records):
        print('Den dokumenterade historikrättelsen är redan genomförd.')
        return
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args])
    original = pd.read_csv(BytesIO(git('show', f'{SOURCE}:{HISTORY}')),
                           compression='gzip', float_precision='round_trip')
    original['date'] = pd.to_datetime(original.date)
    restored = load_score_history()
    for ticker in TICKERS:
        def affected(frame):
            return frame.ticker.eq(ticker) & frame.date.ge('2026-09-30') & frame.date.lt('2026-11-04')
        known = original.loc[affected(original)]
        present = restored.loc[affected(restored)]
        if known.empty or set(known.date) != set(present.date):
            raise ValueError(f'Återställning avbruten: referensdatum stämmer inte för {ticker}')
        restored = pd.concat([restored.loc[~affected(restored)], known], ignore_index=True)
    record = dict(correction_id=CORRECTION_ID, base_commit=git('rev-parse', 'HEAD').decode().strip(),
                  source_commit=SOURCE,
                  reason='Återställ poäng före rapportdagen som skrevs över vid rapportimporten '
                         '4 november. Referens: publicerad historik från 3 november. '
                         'Rapportvärden och rapportdatum bevaras.',
                  **{'from': {t: '2026-09-30' for t in TICKERS}})
    save_score_history(restored)
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(records + [record], ensure_ascii=False, indent=2) + '\n')
    print('Återställd publicerad historik före 4 november: ' + ', '.join(TICKERS))


if __name__ == '__main__':
    restore()
