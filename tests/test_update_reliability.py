"""Regression tests for skipped updates and partially published report data.

All data fixtures below are synthetic examples, not company financial data.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.dashboard_export import write_split_dashboard
from src.fundamentals import normalise_reports
from src.pipeline import _merge_published_news
from src.utils import write_json_atomic
from src.validate_outputs import _validate_report_exports, _validate_split_dashboard

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WRITERS = sorted(
    path for path in WORKFLOWS.glob("*.yml") if "git push" in path.read_text()
)


@pytest.mark.parametrize("path", WRITERS, ids=lambda path: path.stem)
def test_writers_queue_on_same_branch_and_checkout_latest_tip(path: Path) -> None:
    workflow = yaml.safe_load(path.read_text())
    trigger = workflow.get("on", workflow.get(True))
    if "push" in trigger:
        assert trigger["push"]["branches"] == ["main"]
    assert workflow["concurrency"] == {
        "group": "stock-data-${{ github.ref }}",
        "cancel-in-progress": False,
        "queue": "max",
    }
    for job in workflow["jobs"].values():
        checkout = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout@"))
        assert checkout["with"]["ref"] == "${{ github.ref_name }}"
    text = path.read_text()
    assert "origin main" not in text  # a branch run must never write into main
    if "python -m src.pipeline" in text and "git add" in text:
        assert "valuation_score_history.csv.gz" in text


def test_delayed_news_run_cannot_be_skipped_by_wall_clock() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "news_update.yml").read_text())
    # PyYAML's YAML 1.1 loader interprets the Actions key `on` as True.
    trigger = workflow.get("on", workflow.get(True))
    assert trigger["schedule"] == [{"cron": "5 18 * * 1-5", "timezone": "Europe/Stockholm"}]
    steps = workflow["jobs"]["update"]["steps"]
    assert all("if" not in step for step in steps)
    assert "date +" not in "\n".join(step.get("run", "") for step in steps)
    assert any(step.get("run") == "python -m src.news_curated" for step in steps)


def test_manual_eps_rebuilds_after_final_sync() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "add_verified_eps.yml").read_text())
    commands = [step.get("run", "") for step in workflow["jobs"]["add"]["steps"]]
    assert commands.index("python -m src.sync_yahoo_eps_reports") < commands.index(
        "python -m src.pipeline --skip-fetch --skip-dividends"
    ) < commands.index("python -m src.validate_outputs")


def test_daily_update_freezes_scores_only_after_eps_sync() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "daily_update.yml").read_text())
    commands = [step.get("run", "") for step in workflow["jobs"]["update"]["steps"]]
    assert "python -m src.pipeline --defer-score-history" in commands
    assert commands.index("python -m src.sync_yahoo_eps_reports") < commands.index(
        "python -m src.pipeline --skip-fetch --skip-dividends"
    )


def test_historical_rebuild_commits_report_tab_and_events() -> None:
    text = (WORKFLOWS / "enrich_historical_eps.yml").read_text()
    staged = " ".join(line for line in text.splitlines() if "git add" in line)
    assert "docs/data/reports.json" in staged
    assert "docs/data/events.json" in staged
    assert "git restore docs/data/events.json" not in text


def test_market_rebuild_preserves_published_news_without_raw_cache() -> None:
    news = {"event_id": "news:example", "event_type": "news", "published_at": "2026-09-01"}
    old_report = {"event_id": "report:old", "event_type": "report"}
    report = {"event_id": "report:new", "event_type": "report", "published_at": "2026-09-03"}
    assert _merge_published_news([news, old_report], [report]) == [report, news]
    reviewed = {**news, "review_status": "reviewed"}
    assert _merge_published_news([news], [report, reviewed]) == [report, reviewed]


def _report_fixture():
    reports = normalise_reports(pd.DataFrame([{
        "ticker": "EXAMPLE.ST", "report_period": "2026-Q2", "period_end": "2026-07-31",
        "effective_date": "2026-09-03", "eps_ttm": 10.0, "verified": True, "source": "Synthetic example",
    }]))
    stocks = {"EXAMPLE.ST": {
        "latest": {"date": "2026-09-14"},
        "report": {"period": "2026-Q2", "effective_date": "2026-09-03", "eps_ttm": 10.0, "verified": True},
        "candles": [{"date": day} for day in ("2026-09-02", "2026-09-03", "2026-09-14")],
    }}
    events = [{"event_id": "report:EXAMPLE.ST:2026-Q2", "event_type": "report", "event_date": "2026-09-03"}]
    analysis = {"as_of_date": "2026-09-14", "recent": [{"ticker": "EXAMPLE.ST", "report_date": "2026-09-03"}]}
    return reports, stocks, events, analysis


def test_matching_report_exports_pass() -> None:
    _validate_report_exports(*_report_fixture())


@pytest.mark.parametrize("field,value", [("eps_ttm", 9.0), ("eps_ttm", None), ("effective_date", "2026-06-03"), ("verified", False)])
def test_stale_stock_report_is_rejected(field, value) -> None:
    reports, stocks, events, analysis = _report_fixture()
    stocks["EXAMPLE.ST"]["report"][field] = value
    with pytest.raises(ValueError, match="Aktiesidans senaste rapport"):
        _validate_report_exports(reports, stocks, events, analysis)


def test_missing_report_event_is_rejected() -> None:
    reports, stocks, _, analysis = _report_fixture()
    with pytest.raises(ValueError, match="Rapporthändelse saknas"):
        _validate_report_exports(reports, stocks, [], analysis)


@pytest.mark.parametrize("mode", ["missing", "duplicate", "wrong_date"])
def test_incomplete_recent_reports_are_rejected(mode) -> None:
    reports, stocks, events, analysis = _report_fixture()
    if mode == "missing":
        analysis["recent"] = []
    elif mode == "duplicate":
        analysis["recent"] *= 2
    else:
        analysis["recent"][0]["report_date"] = "2026-09-02"
    with pytest.raises(ValueError, match="Rapportfliken avviker"):
        _validate_report_exports(reports, stocks, events, analysis)


def test_report_without_before_price_not_required_in_impact_table() -> None:
    reports, stocks, events, analysis = _report_fixture()
    stocks["EXAMPLE.ST"]["candles"] = [{"date": "2026-09-03"}, {"date": "2026-09-14"}]
    analysis["recent"] = []
    _validate_report_exports(reports, stocks, events, analysis)


def test_split_dashboard_must_match_full_export(tmp_path: Path) -> None:
    _, stocks, _, _ = _report_fixture()
    payload = {"meta": {"generated_at": "2026-09-15T08:00:00+02:00"}, "stocks": stocks}
    write_split_dashboard(tmp_path / "dashboard.json", payload)
    _validate_split_dashboard(payload, tmp_path)
    stale = copy.deepcopy(stocks["EXAMPLE.ST"])
    stale["report"]["eps_ttm"] = 9.0
    write_json_atomic(tmp_path / "dashboard" / "EXAMPLE.ST.json", stale)
    with pytest.raises(ValueError, match="separata datafil"):
        _validate_split_dashboard(payload, tmp_path)
