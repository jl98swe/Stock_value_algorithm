"""Synthetic repository fixture for a bounded, idempotent EPS recovery."""
import json
import subprocess

import pandas as pd

from src.score_history import load_score_history, save_score_history


def test_restoration_preserves_manual_reports_and_post_release_scores(tmp_path, monkeypatch):
    import src.restore_discovered_history as restore
    path = tmp_path / restore.HISTORY
    reports = tmp_path / 'data/fundamentals/reports.csv'
    reports.parent.mkdir(parents=True)
    reports.write_text('synthetic manual input; must be preserved\n')
    original = pd.DataFrame(dict(ticker=['EXAMPLE.ST']*3, date=['2026-09-30','2026-10-19','2026-10-20'], score=[40.,50.,60.]))
    save_score_history(original, path)
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    subprocess.run(['git','-C',str(tmp_path),'add','.'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','Synthetic reference'],check=True)
    sha = subprocess.check_output(['git','-C',str(tmp_path),'rev-parse','HEAD']).decode().strip()
    broken = original.copy(); broken['score'] = [1.,2.,99.]
    save_score_history(broken, path)
    audit = tmp_path / restore.CORRECTIONS
    audit.parent.mkdir(parents=True,exist_ok=True); audit.write_text('[]')
    monkeypatch.setattr(restore,'ROOT',tmp_path)
    monkeypatch.setattr(restore,'CASES',{'EXAMPLE.ST':(sha,'2026-10-20')})
    monkeypatch.setattr(restore,'load_score_history',lambda:load_score_history(path))
    monkeypatch.setattr(restore,'save_score_history',lambda data:save_score_history(data,path))
    restore.restore()
    assert load_score_history(path).score.tolist() == [40.,50.,99.]
    assert reports.read_text() == 'synthetic manual input; must be preserved\n'
    before = path.read_bytes(); record = json.loads(audit.read_text())
    assert record[-1]['base_commit'] == sha
    restore.restore()
    assert path.read_bytes() == before
    assert len(json.loads(audit.read_text())) == 1
