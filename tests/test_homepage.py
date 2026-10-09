from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "docs" / "assets" / "app.js").read_text(encoding="utf-8")
ENHANCEMENTS = (ROOT / "docs" / "assets" / "chart-enhancements.js").read_text(encoding="utf-8")
CSS = (ROOT / "docs" / "assets" / "style.css").read_text(encoding="utf-8")
NEWS = (ROOT / "docs" / "assets" / "company-news.js").read_text(encoding="utf-8")


def test_position_and_signals_panel_is_removed_completely():
    assert 'Position och signaler' not in HTML
    assert 'position-title' not in HTML
    assert 'position-content' not in HTML
    assert "$('position-content')" not in APP
    assert 'Rapportstatus' in HTML
    assert 'report.next_report_end' in APP


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


def test_homepage_news_has_one_title_and_other_histories_have_four_rows():
    assert 'id="news-toggle"' in HTML
    assert 'id="trades-toggle"' in HTML
    assert 'id="dividend-toggle"' in ENHANCEMENTS
    assert "events.slice(0, 1)" in NEWS
    assert 'Visa alla nyheter' in HTML
    assert '<details class="news-details"' in NEWS
    assert "window.companyNews.render" in APP
    assert "trades.slice(0, 4)" in APP
    assert "dividends.slice(0, 4)" in ENHANCEMENTS
    assert "document.getElementById('news-list')" not in ENHANCEMENTS


def test_backtest_and_recent_trade_copy_explain_the_data():
    assert "Historiskt backtest" in HTML
    assert "köp och behåll" in HTML
    assert "0,25 procent courtage" in HTML
    assert "Senaste avslut" in HTML
    assert "b.entry_date.localeCompare(a.entry_date)" in APP
    assert "data.closed_trades" in APP
    assert "data.open_lots" in APP


def test_chart_ranges_and_markers_have_controls():
    for period in ('3m', 'ytd', '3y', '5y'):
        assert f'data-range="{period}"' in HTML
    for marker in ('report', 'dividend', 'news', 'signals'):
        assert f'data-marker="{marker}"' in HTML
    assert "signal.status === 'executed'" in ENHANCEMENTS
    assert "EPS TTM:" in ENHANCEMENTS


def test_report_markers_use_publication_date_and_stay_inside_short_range_chart():
    assert "Rapport för perioden" not in ENHANCEMENTS
    assert "['Rapport', sourceLabel, eventDay(event)]" in ENHANCEMENTS
    assert "reportSourcePriority(event) > reportSourcePriority(previous)" in ENHANCEMENTS
    assert "value: [day, 1]" in ENHANCEMENTS
    assert "name: 'Händelser', type: 'scatter', xAxisIndex: 2, yAxisIndex: 2" in ENHANCEMENTS
    assert "data: signalPoints" in ENHANCEMENTS
    assert "xAxisIndex: [0, 1, 2]" in APP

