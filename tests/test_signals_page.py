from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "docs" / "signals.html").read_text(encoding="utf-8")
OVERVIEW = (ROOT / "docs" / "assets" / "overview.js").read_text(encoding="utf-8")


def test_signals_page_has_separate_upcoming_and_recent_panels():
    assert 'src="./assets/overview.js?v=' in HTML
    assert 'id="upcoming-signals-title">Kommande signaler' in HTML
    assert 'id="recent-signals-title">Senaste signaler' in HTML
    assert 'id="upcoming-signals-body"' in HTML
    assert 'id="recent-signals-body"' in HTML
    assert "grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in HTML
    assert "Återaktiverad" in HTML
    assert "Information om återaktivering" in HTML


def test_recent_signals_include_confirmed_orders_and_cover_twenty_trading_days():
    assert "['executed', 'pending', 'awaiting_next_session'].includes(row.status)" in OVERVIEW
    assert "tradingDates.at(-20)" in OVERVIEW
    assert "b.signal_date.localeCompare(a.signal_date)" in OVERVIEW
    assert "Signal ${prettyDate(row.signal_date)}" in OVERVIEW


def test_recent_signal_copy_explains_execution_fields():
    assert "Fastställda modellsignaler" in HTML
    assert "Datum och kurs fylls i när affären har genomförts" in HTML
    assert "de senaste 20 handelsdagarna, senaste först" in HTML
