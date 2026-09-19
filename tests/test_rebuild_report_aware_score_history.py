import pandas as pd

from src.rebuild_report_aware_score_history import rebuild_report_aware_score_history


def test_rebuild_uses_period_end_state_but_publishes_from_report_date(monkeypatch):
    prices = pd.DataFrame({
        "ticker": ["TEST.ST"] * 6,
        "date": pd.to_datetime([
            "2026-06-29", "2026-06-30", "2026-07-01",
            "2026-07-02", "2026-07-03", "2026-07-06",
        ]),
        "close": [10.0] * 6,
    })
    reports = pd.DataFrame({
        "ticker": ["TEST.ST"],
        "period_end": ["2026-06-30"],
        "report_period": ["2026-Q2"],
        "published_at": [pd.NaT],
        "effective_date": ["2026-07-03"],
        "eps_ttm": [2.0],
        "source": ["TradingView / EARNINGS_PER_SHARE_DILUTED TTM"],
        "verified": [True],
        "verified_at": [pd.NaT],
        "notes": [""],
    })
    seen = {}

    def fake_attach(frame, ticker, available, **kwargs):
        seen["mode"] = kwargs["calculation_mode"]
        seen["period_end"] = available.iloc[0]["period_end"]
        result = frame.copy()
        result["EPS_TTM"] = 2.0
        return result

    def fake_calculate(frame, *, model):
        result = frame.copy()
        result["Score"] = range(len(result))
        return result

    monkeypatch.setattr("src.rebuild_report_aware_score_history.load_stock_currencies", lambda: pd.DataFrame())
    monkeypatch.setattr("src.rebuild_report_aware_score_history.load_fx_history", lambda: pd.DataFrame())
    monkeypatch.setattr("src.rebuild_report_aware_score_history.attach_eps_ttm", fake_attach)
    monkeypatch.setattr("src.rebuild_report_aware_score_history.calculate_valuation", fake_calculate)

    rebuilt = rebuild_report_aware_score_history(
        prices, reports, object(), start_date="2026-06-01", frozen_at="test"
    )

    assert seen["mode"] == "tv_period_end_state"
    assert pd.Timestamp(seen["period_end"]) == pd.Timestamp("2026-06-30")
    assert rebuilt["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-03", "2026-07-06"]


def test_each_report_state_stops_when_the_next_report_is_published(monkeypatch):
    prices = pd.DataFrame({
        "ticker": ["TEST.ST"] * 5,
        "date": pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07"]),
        "close": [10.0] * 5,
    })
    reports = pd.DataFrame({
        "ticker": ["TEST.ST", "TEST.ST"],
        "period_end": ["2026-06-30", "2026-07-05"],
        "report_period": ["2026-Q2", "2026-Q3"],
        "published_at": [pd.NaT, pd.NaT],
        "effective_date": ["2026-07-02", "2026-07-06"],
        "eps_ttm": [2.0, 3.0],
        "source": ["TradingView / EARNINGS_PER_SHARE_DILUTED TTM"] * 2,
        "verified": [True, True],
        "verified_at": [pd.NaT, pd.NaT],
        "notes": ["", ""],
    })
    calls = []

    def fake_attach(frame, ticker, available, **kwargs):
        calls.append(len(available))
        result = frame.copy()
        result["EPS_TTM"] = float(len(available))
        return result

    def fake_calculate(frame, *, model):
        result = frame.copy()
        result["Score"] = result["EPS_TTM"] * 10
        return result

    monkeypatch.setattr("src.rebuild_report_aware_score_history.load_stock_currencies", lambda: pd.DataFrame())
    monkeypatch.setattr("src.rebuild_report_aware_score_history.load_fx_history", lambda: pd.DataFrame())
    monkeypatch.setattr("src.rebuild_report_aware_score_history.attach_eps_ttm", fake_attach)
    monkeypatch.setattr("src.rebuild_report_aware_score_history.calculate_valuation", fake_calculate)

    rebuilt = rebuild_report_aware_score_history(
        prices, reports, object(), start_date="2026-07-01", frozen_at="test"
    )

    assert calls == [1, 2]
    assert rebuilt.set_index("date")["score"].to_dict() == {
        pd.Timestamp("2026-07-02"): 10.0,
        pd.Timestamp("2026-07-03"): 10.0,
        pd.Timestamp("2026-07-06"): 20.0,
        pd.Timestamp("2026-07-07"): 20.0,
    }
