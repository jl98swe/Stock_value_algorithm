"""Synthetic examples; no production data is modified by these tests."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import src.web_eps_submission as web
import src.add_report as reports_module
from src.fundamentals import empty_reports
from src.manual_reports import append_manual_submission, load_manual_submissions, publish_manual_reports


@pytest.fixture
def payload(monkeypatch):
    monkeypatch.setattr(web, "load_stock_currencies", lambda: pd.DataFrame([{"ticker": "TEST.ST", "price_currency": "SEK", "report_currency": "EUR"}]))
    return dict(request_id="a" * 32, ticker="TEST.ST", report_period="2026-Q3", period_end="2026-09-30", published_at="2026-10-23", metric="eps_ttm", value=2.78, currency="SEK", source="TradingView", notes="Exempel")


@pytest.mark.parametrize("change", [
    {"value": True}, {"value": float("inf")}, {"value": "2,78"}, {"ticker": "UNKNOWN.ST"},
    {"period_end": "2026-02-30"}, {"published_at": "2099-01-01"}, {"request_id": "../bad"},
    {"source": ""}, {"metric": "reportedEPS"}, {"currency": ""},
    {"notes": "report_currency=USD"}, {"notes": "manual_report_submission_v1"},
])
def test_invalid_inputs_are_rejected_before_writes(payload, change):
    with pytest.raises(ValueError):
        web.validate_submission({**payload, **change}, today=date(2026, 10, 26))


def setup_storage(monkeypatch, tmp_path):
    audit = tmp_path / "audit.csv"
    monkeypatch.setattr(web, "ROOT", tmp_path)
    monkeypatch.setattr(web, "load_manual_submissions", lambda: load_manual_submissions(audit))
    monkeypatch.setattr(web, "append_manual_submission", lambda **kw: append_manual_submission(**kw, path=audit))
    monkeypatch.setattr(web, "publish_manual_reports", lambda: publish_manual_reports(pd.DataFrame(), audit_path=audit, output_path=tmp_path / "manual.json"))
    return audit


def test_currency_review_is_saved_without_changing_canonical_ttm(payload, monkeypatch, tmp_path):
    audit = setup_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "add_report", lambda **kw: pytest.fail("Must not apply foreign-currency EPS"))
    result = web.submit({**payload, "currency": "EUR"})
    assert result["status"] == "currency_review"
    assert result["result_eps_ttm"] is None
    row = load_manual_submissions(audit).iloc[0]
    assert row["eps_currency"] == "EUR" and row["result_eps_ttm"] == ""
    assert web.submit({**payload, "currency": "EUR"}) == result
    assert len(load_manual_submissions(audit)) == 1
    with pytest.raises(ValueError, match="annan inmatning"):
        web.submit({**payload, "currency": "EUR", "value": 3})


def test_missing_history_keeps_quarterly_value_and_warning(payload, monkeypatch, tmp_path):
    audit = setup_storage(monkeypatch, tmp_path)
    def missing(**kw):
        raise ValueError("Saknar jämförbar EPS föregående år")
    monkeypatch.setattr(web, "derive_manual_eps_ttm_safe", missing)
    captured = {}
    monkeypatch.setattr(web, "upsert_manual_quarterly_eps", lambda **kw: captured.update(kw))
    monkeypatch.setattr(web, "add_report", lambda **kw: pytest.fail("Must not replace active TTM"))
    result = web.submit({**payload, "metric": "quarterly_eps", "value": -0.5})
    assert result["status"] == "pending_ttm"
    assert captured["eps"] == -0.5
    assert "föregående år" in result["reason"]
    assert load_manual_submissions(audit).iloc[0]["status"] == "pending_ttm"


def test_direct_sek_ttm_overrides_foreign_reporting_currency(payload, monkeypatch, tmp_path):
    audit = setup_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(reports_module, "load_reports", empty_reports)
    monkeypatch.setattr(reports_module, "save_reports", lambda frame: None)
    monkeypatch.setattr(reports_module, "load_stock_currencies", web.load_stock_currencies)
    monkeypatch.setattr(reports_module, "append_manual_submission", lambda **kw: append_manual_submission(**kw, path=audit))
    monkeypatch.setattr(reports_module, "publish_manual_reports", lambda frame: None)
    result = web.submit({**payload, "value": 0})
    assert result["status"] == "applied" and result["result_eps_ttm"] == 0
    row = load_manual_submissions(audit).iloc[0]
    assert row["eps_currency"] == "SEK"
    assert row["submission_id"] == payload["request_id"]
    assert web.submit({**payload, "value": 0}) == result
    assert len(load_manual_submissions(audit)) == 1
