from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import src.add_report as add_report_module
from src.fundamentals import empty_reports
from src.manual_reports import append_manual_submission, publish_manual_reports
from src.sync_yahoo_eps_reports import AUTO_MARKER, _is_replaceable_generated_report


def test_manual_submission_is_saved_and_published(tmp_path: Path) -> None:
    audit = tmp_path / "report_submissions.csv"
    output = tmp_path / "manual_reports.json"
    append_manual_submission(
        ticker="PLAZ-B.ST",
        report_period="2026-Q2",
        period_end="2026-06-30",
        published_at="2026-07-03T07:00:00+02:00",
        effective_date="2026-07-03",
        input_metric="eps_ttm",
        input_eps=6.119,
        result_eps_ttm=6.119,
        eps_currency="SEK",
        source="TradingView",
        notes="",
        path=audit,
    )

    payload = publish_manual_reports(pd.DataFrame(), audit_path=audit, output_path=output)

    assert payload["submissions"][0]["input_metric"] == "eps_ttm"
    assert payload["submissions"][0]["result_eps_ttm"] == "6.119"
    assert json.loads(output.read_text(encoding="utf-8"))["submissions"][0]["ticker"] == "PLAZ-B.ST"


def test_canonical_manual_report_is_visible_without_audit_row(tmp_path: Path) -> None:
    reports = pd.DataFrame(
        [
            {
                "ticker": "PLAZ-B.ST",
                "period_end": "2026-06-30",
                "report_period": "2026-Q2",
                "published_at": "2026-07-03T05:00:00Z",
                "effective_date": "2026-07-03",
                "eps_ttm": 6.119,
                "source": "TradingView / EARNINGS_PER_SHARE_DILUTED TTM",
                "verified": True,
                "verified_at": "2026-09-19T10:00:00Z",
                "notes": "",
            }
        ]
    )
    payload = publish_manual_reports(
        reports,
        audit_path=tmp_path / "missing.csv",
        output_path=tmp_path / "manual_reports.json",
    )

    item = payload["submissions"][0]
    assert item["origin"] == "canonical"
    assert item["input_eps"] == "6.119"


def test_review_page_distinguishes_strategy_eps_from_yahoo() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "docs" / "review.html").read_text(encoding="utf-8")
    script = (root / "docs" / "assets" / "review.js").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "add_verified_eps.yml").read_text(encoding="utf-8")

    assert "EPS TTM (direkt värde)" in html
    assert "Manuella rapporteringar" in html
    assert "Aktivt EPS TTM i strategin" in script
    assert "Yahoo trailing EPS TTM" not in script
    assert "Yahoo-jämförelse" not in script
    assert "Senast sparad Yahoo trailing EPS TTM" not in script
    assert "type: choice" in workflow
    assert "python -m src.earnings" not in workflow
    assert "python -m src.quarterly_eps" not in workflow


def test_direct_ttm_is_applied_and_audited(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(add_report_module, "load_reports", empty_reports)
    monkeypatch.setattr(add_report_module, "save_reports", lambda frame: None)
    monkeypatch.setattr(
        add_report_module,
        "load_stock_currencies",
        lambda: pd.DataFrame([{"ticker": "PLAZ-B.ST", "report_currency": "SEK"}]),
    )
    monkeypatch.setattr(
        add_report_module,
        "append_manual_submission",
        lambda **kwargs: captured.update(kwargs),
    )
    monkeypatch.setattr(add_report_module, "publish_manual_reports", lambda reports: None)

    reports = add_report_module.add_report(
        ticker="PLAZ-B.ST",
        report_period="2026-Q2",
        period_end="2026-06-30",
        published_at="2026-07-03",
        eps_ttm=6.119,
        source="TradingView",
    )

    assert reports.iloc[-1]["eps_ttm"] == 6.119
    assert captured["input_metric"] == "eps_ttm"
    assert captured["result_eps_ttm"] == 6.119


def test_manual_eps_always_has_priority_over_yahoo() -> None:
    manual_direct = pd.Series({"notes": "manual_report_submission_v1; input_metric=eps_ttm"})
    manual_quarterly = pd.Series({"notes": "manual_quarterly_eps_derived_v1"})
    yahoo = pd.Series({"notes": f"{AUTO_MARKER}; metric=trailingDilutedEPS"})

    assert not _is_replaceable_generated_report(manual_direct)
    assert not _is_replaceable_generated_report(manual_quarterly)
    assert _is_replaceable_generated_report(yahoo)
