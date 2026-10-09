"""Refresh only upcoming-report fields in the existing dashboard exports."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import ROOT
from .events import load_report_calendar
from .fundamentals import normalise_reports
from .pipeline import _report_payload
from .reporting import _combined_schedule, load_auto_report_calendar
from .utils import write_json_atomic


def refresh_report_status(
    dashboard_path: Path = ROOT / 'docs/data/dashboard.json',
    *, schedule: pd.DataFrame | None = None, as_of: pd.Timestamp | None = None,
) -> int:
    dashboard = json.loads(dashboard_path.read_text(encoding='utf-8'))
    manual = load_report_calendar()
    if schedule is None:
        schedule = _combined_schedule(load_auto_report_calendar(), manual)
    empty_reports = normalise_reports(pd.DataFrame())
    changed = 0
    for ticker, stock in dashboard['stocks'].items():
        upcoming = {key:value for key,value in _report_payload(
            ticker, empty_reports, manual, schedule=schedule, as_of=as_of,
        ).items() if key.startswith('next_report')}
        report = stock.setdefault('report', {})
        split_path = dashboard_path.parent / dashboard_path.stem / f'{ticker}.json'
        split = json.loads(split_path.read_text(encoding='utf-8'))
        split_report = split.setdefault('report', {})
        if any(report.get(key) != value or split_report.get(key) != value for key,value in upcoming.items()):
            report.update(upcoming)
            split_report.update(upcoming)
            write_json_atomic(split_path, split)
            changed += 1
    if changed:
        write_json_atomic(dashboard_path, dashboard)
    return changed


if __name__ == '__main__':
    print(f'Rapportstatus uppdaterad för {refresh_report_status()} aktier; kurser, EPS och poäng oförändrade.')
