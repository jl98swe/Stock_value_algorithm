"""Check every audited recovery and optionally update the published audit."""
from io import BytesIO
import argparse
import json
import subprocess

import numpy as np
import pandas as pd

from .config import ROOT
from .restore_discovered_history import CASES, CORRECTION_ID
from .score_history import load_score_history
from .history_guard import CORRECTIONS, HISTORY


def verify(*, update_audit=False):
    def git(*args):
        return subprocess.check_output(['git','-C',str(ROOT),*args])
    records = json.loads((ROOT / CORRECTIONS).read_text())
    recovery = next((r for r in records if r.get('correction_id') == CORRECTION_ID), None)
    if recovery is None:
        raise ValueError('Dokumenterad återställning saknas')
    cases = dict(CASES)
    for ticker in ['CLA-B.ST','SINT.ST','CIBUS.ST','KAMBI.ST','MCOV-B.ST']:
        cases[ticker] = ('6b69657027c54546ebf2576bd393e78eb4616103', '2026-11-04')
    actual = load_score_history()
    checked = []
    for ticker, (source, before) in cases.items():
        old = pd.read_csv(BytesIO(git('show',f'{source}:{HISTORY}')), compression='gzip',float_precision='round_trip')
        old.date = pd.to_datetime(old.date)
        old = old.loc[old.ticker.eq(ticker) & old.date.ge('2026-09-30') & old.date.lt(before)]
        compare = old.merge(actual.loc[actual.ticker.eq(ticker)],on=['ticker','date'],suffixes=('_old','_new'),how='left',validate='one_to_one')
        if not np.isclose(compare.score_old,compare.score_new,rtol=0,atol=1e-9).all():
            raise ValueError(f'Återställd historik avviker från publicerad referens: {ticker}')
        checked.append(ticker)
    # The user-verified report submissions are not historical score backups.
    # They must survive byte-for-byte, regardless of the score repair.
    path = 'data/manual/report_submissions.csv'
    if git('show',f'{recovery["base_commit"]}:{path}') != (ROOT/path).read_bytes():
        raise ValueError('Manuella EPS-registreringar har ändrats vid återställningen')
    all_trades = json.loads((ROOT/'docs/data/backtests/all.json').read_text())
    for ticker, first_bad, known in [('ALLEI.ST','2026-10-27','2026-11-01'),
                                    ('EPI-A.ST','2026-10-29','2026-11-01'),
                                    ('NDA-SE.ST','2026-10-16','2026-10-31'),
                                    ('SEB-A.ST','2026-10-23','2026-10-31')]:
        trades = all_trades['report_avoidance']['closed_trades'] + all_trades['report_avoidance']['open_lots']
        bad = [t for t in trades if t['ticker']==ticker and first_bad <= t['entry_signal_date'] < known]
        if bad:
            raise ValueError(f'Kalenderköp före observationstid kvarstår: {ticker}')
    for ticker, side, forbidden in [('AZN.ST','entry_date','2026-10-05'),('FOI-B.ST','exit_date','2026-10-02')]:
        rows = all_trades['standard']['closed_trades'] + all_trades['standard']['open_lots']
        if any(r['ticker']==ticker and r.get(side)==forbidden for r in rows):
            raise ValueError(f'Felaktig modellaffär kvarstår: {ticker} {forbidden}')
    if update_audit:
        path = ROOT/'reference/history_audit_all_stocks_2026-11-04.csv'
        table = pd.read_csv(path,keep_default_na=False)
        assert len(table)==119 and table.ticker.nunique()==119
        for index,row in table.iterrows():
            if row.ticker in checked:
                table.loc[index,'eps_history_restored'] = True
                table.loc[index,'remaining_pre_report_score_dates'] = 0
                table.loc[index,'first_remaining_date'] = ''
                table.loc[index,'last_remaining_date'] = ''
            if str(row.calendar_dependent_retroactive_buy).lower()=='true' or row.ticker=='AZN.ST':
                table.loc[index,'calendar_history_restored'] = True
        table['restoration_base_commit'] = recovery['base_commit']
        table.to_csv(path,index=False)
        path = ROOT/'reference/history_audit_2026-11-04.md'
        text = path.read_text()
        for phrase in ['Kvar att återställa före 20 oktober','Kvar att återställa före 22 oktober',
                       'Kvar att återställa före 30 oktober','Kvar att återställa före 3 november',
                       'Kvar att återställa före 5 november']:
            text = text.replace(phrase,'Återställd')
        heading = '## Efterföljande återställning 4 november 2026'
        if heading not in text:
            text = text.replace('## Resultat',heading+'\n\nSamtliga tio EPS-fall är nu återställda och kontrollerade mot respektive\npublicerad referens före felet. Senare dagar som saknade en referens räknades\nom med endast de rapporter som var publicerade den dagen. De verifierade\nmanuella rapportregistreringarna är bevarade byte för byte.\n\nDe fyra kalenderköpen och AstraZenecas kalenderberoende äldre affärer har\nrättats med arkiverad observationstid. För nya kalenderdatum används den\nförsta sparade observationen även när rapporten senare blir historisk.\nEn migrationslista bevarar redan publicerade äldre simuleringar för övriga\naktier; den gör inget påstående om när deras kalenderinformation först var känd.\nEn uppdaterad kalender får inte ge tillåtelse till köp före observationen.\nÄldre simuleringar bevaras, med en uttrycklig rättelse för AstraZenecas\nrapport 30 oktober enligt kalenderobservationen 15 september.\n\nStatusen i tabellen och 119-radersfilen är uppdaterad efter återställningen.\nDen ursprungliga granskningsmetoden och fynden nedan behålls som kontrollspår.\n\n## Resultat')
        text = text.replace('Fem aktiers historik är återställd i den granskade\nversionen. Fem ytterligare har kvar ändrad historik och behöver rättas separat.',
                            'Vid granskningen var fem aktier återställda och fem ytterligare återstod.\nEfterföljande återställning ovan omfattar samtliga tio.')
        text = text.replace('Alla fem\n   tidigare återställda aktier matchar referensen. De fem nyupptäckta gör det inte.',
                            'Vid granskningen matchade de fem tidigare återställda aktierna\n   referensen medan de fem nyupptäckta inte gjorde det. Efter återställningen\n   matchar samtliga tio sina respektive referenser.')
        path.write_text(text)
    print('Återställning verifierad: 10 EPS-fall, 4 kalenderfall, manuella rapporter bevarade, 119 aktier i granskningsfilen.')
    return checked


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--update-audit',action='store_true')
    verify(update_audit=parser.parse_args().update_audit)
