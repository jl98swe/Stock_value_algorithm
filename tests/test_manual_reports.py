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
    assert "Tidigare inmatningar" in html
    assert "Nuvarande EPS TTM" in script
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


def test_latest_dated_conversion_is_not_hidden_by_an_undated_old_report(tmp_path):
    from src.eps_conversion import convert_ttm
    fx = pd.DataFrame([dict(date='2026-11-03',rate=10,base_currency='EUR',quote_currency='SEK')])
    notes = convert_ttm(1.3,'EUR','SEK','2026-11-04',fx)['notes'] + '; report_currency=SEK'
    rows = pd.DataFrame([
        dict(ticker='EXAMPLE.ST',report_period='2026-Q3',period_end='2026-09-30',
             effective_date='2026-11-04',verified=True,eps_ttm=13,source='Example issuer',notes=notes),
        dict(ticker='EXAMPLE.ST',report_period='2018-Q3',period_end='2018-09-30',
             effective_date=None,verified=True,eps_ttm=4,source='TradingView',notes='report_currency=SEK')])
    data = publish_manual_reports(rows,audit_path=tmp_path/'missing.csv',output_path=tmp_path/'manual.json')
    assert len(data['submissions']) == 1
    assert data['submissions'][0]['report_period'] == '2026-Q3'
    assert data['submissions'][0]['eps_conversion']['original_eps_ttm'] == 1.3


def test_manual_report_supersedes_generated_alias_and_preserves_prior_manual(monkeypatch):
    from src.fundamentals import normalise_reports, latest_verified_report
    # Synthetic example: alias and manual period share a corrected release day.
    old = normalise_reports(pd.DataFrame([
        dict(ticker='EXAMPLE.ST', report_period='2026-Q2', period_end='2026-06-30',
             effective_date='2026-07-21', eps_ttm=5.69, verified=True,
             source='TradingView / EARNINGS_PER_SHARE_DILUTED TTM'),
        dict(ticker='EXAMPLE.ST', report_period='YAHOO-2026-09-30', period_end='2026-09-30',
             effective_date='2026-10-28', eps_ttm=.379, verified=True,
             source='Yahoo Finance / trailingDilutedEPS', notes=AUTO_MARKER)]))
    monkeypatch.setattr(add_report_module, 'load_reports', lambda: old.copy())
    monkeypatch.setattr(add_report_module, 'save_reports', lambda frame: None)
    monkeypatch.setattr(add_report_module, 'load_stock_currencies', lambda: pd.DataFrame([
        dict(ticker='EXAMPLE.ST',report_currency='SEK',price_currency='SEK')]))
    monkeypatch.setattr(add_report_module, 'append_manual_submission', lambda **kwargs: None)
    monkeypatch.setattr(add_report_module, 'publish_manual_reports', lambda frame: None)
    result = add_report_module.add_report(ticker='EXAMPLE.ST',report_period='2026-Q3',
        period_end='2026-09-30',published_at='2026-10-28T15:00:00+01:00',
        eps_ttm=5.78,eps_currency='SEK',source='Synthetic issuer report')
    assert latest_verified_report('EXAMPLE.ST',result).eps_ttm == 5.78
    assert result.loc[result.report_period.eq('2026-Q2'),'eps_ttm'].tolist() == [5.69]
    assert len(result) == 2
    assert old.loc[old.report_period.str.startswith('YAHOO-'),'eps_ttm'].tolist() == [.379]
