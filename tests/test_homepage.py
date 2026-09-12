from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "docs" / "assets" / "app.js").read_text(encoding="utf-8")
ENHANCEMENTS = (ROOT / "docs" / "assets" / "chart-enhancements.js").read_text(encoding="utf-8")
CSS = (ROOT / "docs" / "assets" / "style.css").read_text(encoding="utf-8")


def test_decorative_data_badges_and_trade_workflow_link_are_removed():
    assert 'id="data-badge"' not in HTML
    assert 'id="quality-badge"' not in HTML
    assert 'id="trade-workflow-link"' not in HTML
    assert "$('data-badge')" not in APP
    assert "$('quality-badge')" not in APP
    assert "$('trade-workflow-link')" not in APP


def test_fundamental_lock_respects_hidden_attribute():
    assert 'id="lock-alert" class="lock-alert" hidden' in HTML
    assert 'id="lock-badge" class="badge badge-warning" hidden' in HTML
    assert "setHidden('lock-alert', !locked)" in APP
    assert "setHidden('lock-badge', !locked)" in APP
    assert "[hidden] { display: none !important; }" in CSS


def test_homepage_histories_are_collapsed_to_four_rows():
    assert 'id="news-toggle"' in HTML
    assert 'id="trades-toggle"' in HTML
    assert 'id="dividend-toggle"' in ENHANCEMENTS
    assert "events.slice(0, 4)" in APP
    assert "trades.slice(0, 4)" in APP
    assert "dividends.slice(0, 4)" in ENHANCEMENTS
    assert "news.slice(0, 4)" in ENHANCEMENTS


def test_backtest_and_recent_trade_copy_explain_the_data():
    assert "Historiskt backtest" in HTML
    assert "samma exekverade köp och sälj" in HTML
    assert "courtage är 0,25 procent" in HTML
    assert "Senaste avslut" in HTML
    assert "b.execution_date.localeCompare(a.execution_date)" in APP
