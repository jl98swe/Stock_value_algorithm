"""Synthetic examples of delisted stocks and issuer calendar fallback."""
import pandas as pd

from src.listing_status import active_tickers, trading_rows
import src.reporting as reporting


def test_delisting_stops_live_collection_but_keeps_pre_delisting_history(tmp_path):
    status = tmp_path / "listing.csv"
    status.write_text("ticker,last_trading_date\nEXAMPLE.ST,2026-09-22\n")
    assert active_tickers(["EXAMPLE.ST", "OTHER.ST"], today="2026-09-22", path=status) == ["EXAMPLE.ST", "OTHER.ST"]
    assert active_tickers(["EXAMPLE.ST", "OTHER.ST"], today="2026-09-23", path=status) == ["OTHER.ST"]
    prices = pd.DataFrame(dict(ticker=["EXAMPLE.ST"] * 2 + ["OTHER.ST"],
        date=["2026-09-22", "2026-09-23", "2026-09-23"], close=[10, 99, 20]))
    kept = trading_rows(prices, path=status)
    assert kept.close.tolist() == [10, 20]


def test_mfn_calendar_filters_dividends_annual_reports_and_estimated_times():
    html = '''<table class="table-calender"><tbody>
      <tr><td>2026-10-07</td><td>09:30</td><td>Kvartalsrapport 2026-Q3</td></tr>
      <tr><td>2026-10-06</td><td>10:00</td><td>X-dag utdelning</td></tr>
      <tr><td>2026-10-06</td><td>10:00</td><td>Årsredovisning</td></tr>
      <tr><td>2027-02-05</td><td>09:30</td><td>Bokslutskommuniké 2026</td></tr>
      <tr><td>2026-07-08</td><td>-</td><td>Kvartalsrapport 2026-Q2</td></tr>
      </tbody></table>'''
    rows = reporting._mfn_rows(html, "EXAMPLE.ST", pd.Timestamp("2026-10-06"))
    assert rows.report_date_start.tolist() == [pd.Timestamp("2026-10-07")]
    assert rows.source.tolist() == [reporting.MFN_SOURCE]
    assert rows.expected_eps.isna().all()


def test_borskollen_share_classes_share_release_and_longer_horizon(monkeypatch):
    monkeypatch.setattr(reporting, "_metadata", lambda: pd.DataFrame(dict(ticker=["EXAMPLE-A.ST", "EXAMPLE-B.ST"])))
    class Response:
        def __init__(self, day): self.day = day
        def raise_for_status(self): pass
        def json(self):
            return {"items": [dict(tagTicker="EXAMPLE B", tagCountry="Sverige", reportDate=self.day)] if self.day == "2026-12-10" else []}
    class Session:
        headers = {}
        def get(self, url, params, timeout): return Response(params["date"])
    rows = reporting._borskollen_rows(observed_date="2026-10-06", session=Session())
    # The feed uses a space instead of the strategy ticker's hyphen.
    assert sorted(rows.ticker) == ["EXAMPLE-A.ST", "EXAMPLE-B.ST"]


def test_daily_fallback_fills_missing_tomorrow_report_and_preserves_manual_date(tmp_path, monkeypatch):
    monkeypatch.setattr(reporting, "_metadata", lambda: pd.DataFrame(dict(ticker=["EXAMPLE.ST"])))
    monkeypatch.setattr(reporting, "load_report_calendar", lambda: pd.DataFrame())
    sources = tmp_path / "sources.csv"
    sources.write_text("ticker,status,mfn_url\nEXAMPLE.ST,resolved,https://mfn.se/all/a/example\n")
    class Response:
        text = '<table class="table-calender"><tbody><tr><td>2026-10-07</td><td>09:30</td><td>Kvartalsrapport</td></tr></tbody></table>'
        def raise_for_status(self): pass
    class Session:
        def get(self, url, timeout): return Response()
    rows = reporting.refresh_gap_calendar(today="2026-10-06", session=Session(),
        reports=pd.DataFrame([dict(ticker="EXAMPLE.ST", effective_date="2026-08-07", verified=True)]),
        current_path=tmp_path / "current.csv", history_path=tmp_path / "history.csv", sources_path=sources)
    assert rows.ticker.tolist() == ["EXAMPLE.ST"]
    assert rows.report_date_start.iloc[0] == pd.Timestamp("2026-10-07")


def test_date_only_manual_calendar_rows_survive_timestamp_rows(tmp_path):
    from src.events import load_report_calendar
    path = tmp_path / "calendar.csv"
    path.write_text("ticker,scheduled_at,verified\nONE.ST,2026-10-23T07:00:00+02:00,True\nTWO.ST,2026-10-07,True\n")
    rows = load_report_calendar(path)
    assert rows.scheduled_at.notna().all()
    assert rows.scheduled_at.dt.strftime("%Y-%m-%d").tolist() == ["2026-10-23", "2026-10-07"]


def test_mfn_reserve_never_overrides_a_user_verified_date():
    from src.events import load_report_calendar
    automatic = reporting._mfn_rows('<table class="table-calender"><tbody><tr><td>2026-10-08</td><td>09:30</td><td>Kvartalsrapport</td></tr></tbody></table>',
        "EXAMPLE.ST", pd.Timestamp("2026-10-06"))
    manual = load_report_calendar().iloc[:0].copy()
    manual = pd.concat([manual, pd.DataFrame([dict(ticker="EXAMPLE.ST", report_period="", scheduled_at=pd.Timestamp("2026-10-07", tz="UTC"),
        lock_from_date=pd.NaT, source="Synthetic verified date", url="", verified=True,
        expected_eps=None, expected_eps_currency="", expected_eps_metric="", expected_eps_verified=False)])], ignore_index=True)
    rows = reporting._combined_schedule(automatic, manual)
    assert rows.report_date_start.tolist() == [pd.Timestamp("2026-10-07")]


def test_daily_mfn_targets_respect_60_days_and_known_14_day_window(monkeypatch):
    tickers = ["OLD", "RECENT", "URGENT", "LATER", "UNKNOWN", "UNVERIFIED", "FUTURE", "DELISTED"]
    monkeypatch.setattr(reporting, "_metadata", lambda: pd.DataFrame(dict(ticker=tickers)))
    monkeypatch.setattr(reporting, "active_tickers", lambda tickers, today: [t for t in tickers if t != "DELISTED"])
    schedule = pd.DataFrame(dict(ticker=["URGENT", "LATER", "OLD"],
        report_date_start=pd.to_datetime(["2026-10-20", "2026-10-21", "2026-10-05"]),
        report_date_end=pd.to_datetime(["2026-10-20", "2026-10-21", "2026-10-05"])))
    reports = pd.DataFrame(dict(ticker=["OLD", "OLD", "RECENT", "UNVERIFIED", "FUTURE", "DELISTED"],
        effective_date=["2026-05-01", "2026-08-07", "2026-08-08", "2026-01-01", "2026-10-07", "2026-01-01"],
        verified=[True, True, True, False, True, True]))
    assert reporting._mfn_targets(schedule, pd.Timestamp("2026-10-06"), reports=reports) == {"OLD", "URGENT"}
    # The weekly sweep includes recent, distant and unknown dates too.
    assert reporting._mfn_targets(schedule, pd.Timestamp("2026-10-06"), reports=reports, all_active=True) == set(tickers) - {"DELISTED"}


def test_daily_mfn_uses_actual_publication_day_when_effective_day_is_later(monkeypatch):
    monkeypatch.setattr(reporting, "_metadata", lambda: pd.DataFrame(dict(ticker=["EXAMPLE.ST"])))
    schedule = pd.DataFrame(columns=["ticker", "report_date_start", "report_date_end"])
    reports = pd.DataFrame([dict(ticker="EXAMPLE.ST", published_at="2026-08-07T18:00:00+02:00",
        effective_date="2026-08-10", verified=True)])
    assert reporting._mfn_targets(schedule, pd.Timestamp("2026-10-06"), reports=reports) == {"EXAMPLE.ST"}


def test_weekly_yahoo_entry_point_also_checks_all_active_mfn_issuers(monkeypatch):
    import sys
    calls = []
    monkeypatch.setattr(sys, "argv", ["reporting", "--source", "yahoo"])
    monkeypatch.setattr(reporting, "update_report_calendar", lambda **kwargs: calls.append("yahoo"))
    monkeypatch.setattr(reporting, "refresh_gap_calendar", lambda **kwargs: calls.append(kwargs))
    reporting.main()
    assert calls == ["yahoo", {"all_active": True}]
