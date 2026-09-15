from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "docs" / "signals.html").read_text(encoding="utf-8")
OVERVIEW = (ROOT / "docs" / "assets" / "overview.js").read_text(encoding="utf-8")


def test_signals_page_has_separate_upcoming_and_recent_panels():
    assert "overview.js?v=20260915-1" in HTML
    assert 'id="upcoming-signals-title">Kommande signaler' in HTML
    assert 'id="recent-signals-title">Senaste signaler' in HTML
    assert 'id="upcoming-signals-body"' in HTML
    assert 'id="recent-signals-body"' in HTML
    assert "grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in HTML
    assert "Återaktiverad" in HTML
    assert "Information om återaktivering" in HTML


def test_recent_signals_are_executed_only_and_cover_twenty_trading_days():
    assert "row.status === 'executed' && row.execution_date" in OVERVIEW
    assert "tradingDates.at(-20)" in OVERVIEW
    assert "b.execution_date.localeCompare(a.execution_date)" in OVERVIEW
    assert "Signal ${prettyDate(row.signal_date)}" in OVERVIEW


def test_recent_signal_copy_explains_that_records_are_model_executions():
    assert "Endast exekverade modellsignaler" in HTML
    assert "de senaste 20 handelsdagarna, senaste först" in HTML
