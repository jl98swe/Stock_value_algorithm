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
    {"notes": "eps_fx_fallback_v1; fx_rate=10"},
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
    def no_rate(**kw):
        raise ValueError("Saknar valutakurs före rapportdagen")
    monkeypatch.setattr(web, "add_report", no_rate)
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


def test_foreign_ttm_uses_pinned_fx_and_retry_keeps_original_input(payload, monkeypatch, tmp_path):
    import src.eps_conversion as conversion
    monkeypatch.setattr(conversion, 'record_conversion', lambda row: None)
    import src.fx as fx_module
    from src.eps_conversion import conversion_metadata
    audit = setup_storage(monkeypatch, tmp_path)
    captured = []
    monkeypatch.setattr(reports_module, "load_reports", empty_reports)
    monkeypatch.setattr(reports_module, "save_reports", lambda frame: captured.append(frame))
    monkeypatch.setattr(reports_module, "load_stock_currencies", web.load_stock_currencies)
    monkeypatch.setattr(reports_module, "append_manual_submission", lambda **kw: append_manual_submission(**kw, path=audit))
    monkeypatch.setattr(reports_module, "publish_manual_reports", lambda frame: None)
    monkeypatch.setattr(fx_module, "load_fx_history", lambda: pd.DataFrame([
        dict(date='2026-10-22',base_currency='EUR',quote_currency='SEK',rate=10),
        dict(date='2026-10-23',base_currency='EUR',quote_currency='SEK',rate=20)]))
    item = {**payload, 'value': 1.3, 'currency': 'EUR'}
    result = web.submit(item)
    assert result['status'] == 'applied' and result['currency'] == 'SEK'
    assert result['result_eps_ttm'] == 13
    assert conversion_metadata(captured[0].iloc[0])['rate_date'] == '2026-10-22'
    assert web.submit(item) == result
    assert len(load_manual_submissions(audit)) == 1


def test_fx_cannot_replace_existing_manual_sek_ttm(payload, monkeypatch):
    from src.fundamentals import normalise_reports
    import src.fx as fx_module
    existing = normalise_reports(pd.DataFrame([dict(ticker='TEST.ST',report_period='2026-Q3',
        period_end='2026-09-30',effective_date='2026-10-23',eps_ttm=13,
        verified=True,source='TradingView / diluted',notes='report_currency=SEK')]))
    monkeypatch.setattr(reports_module, 'load_reports', lambda: existing)
    monkeypatch.setattr(reports_module, 'load_stock_currencies', web.load_stock_currencies)
    monkeypatch.setattr(fx_module,'load_fx_history', lambda:pd.DataFrame([
        dict(date='2026-10-22',base_currency='EUR',quote_currency='SEK',rate=10)]))
    monkeypatch.setattr(reports_module,'save_reports',lambda _:pytest.fail('Must preserve manual TTM'))
    with pytest.raises(ValueError,match='manuellt EPS'):
        reports_module.add_report(ticker='TEST.ST',report_period='2026-Q3',period_end='2026-09-30',
            published_at='2026-10-23',source='Example issuer',eps_ttm=1.3,eps_currency='EUR')
