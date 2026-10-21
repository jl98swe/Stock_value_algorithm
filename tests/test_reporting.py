from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.reporting as reporting
from src.fundamentals import normalise_reports
from src.quarterly_eps import DILUTED_METRIC


def _metadata() -> pd.DataFrame:
    return pd.DataFrame(
        [{"ticker": "TEST.ST", "company": "Testbolaget", "price_currency": "SEK", "report_currency": "SEK"}]
    )


def _calendar_row(**updates: object) -> dict[str, object]:
    row = {
        "ticker": "TEST.ST",
        "report_date_start": "2026-10-08",
        "report_date_end": "2026-10-08",
        "date_status": "confirmed",
        "expected_eps": 1.35,
        "expected_eps_low": 1.2,
        "expected_eps_high": 1.5,
        "expected_eps_currency": "SEK",
        "expected_eps_metric": reporting.UNVERIFIED_ESTIMATE_METRIC,
        "expected_eps_verified": False,
        "source": reporting.REPORT_SOURCE,
        "observed_date": "2026-10-01",
    }
    row.update(updates)
    return row


def _reports() -> pd.DataFrame:
    return normalise_reports(
        pd.DataFrame(
            [
                {
                    "ticker": "TEST.ST",
                    "period_end": "2026-06-30",
                    "report_period": "2026-Q2",
                    "published_at": "2026-07-20T07:00:00+02:00",
                    "effective_date": "2026-07-20",
                    "eps_ttm": 4.0,
                    "source": "Bolagets rapport",
                    "verified": True,
                    "verified_at": "2026-07-20T08:00:00Z",
                    "notes": "report_currency=SEK",
                }
            ]
        )
    )


def _quarterly() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "period_end": "2025-09-30",
                "report_date": "2025-10-20",
                "observed_date": "2026-09-01",
                "metric": DILUTED_METRIC,
                "eps": 1.1,
                "eps_currency": "SEK",
                "source": "Yahoo Finance / quarterlyDilutedEPS",
            }
        ]
    )


def test_yahoo_calendar_estimate_is_explicitly_unverified() -> None:
    row = reporting._parse_yahoo_calendar(
        "TEST.ST",
        {
            "Earnings Date": [pd.Timestamp("2026-10-08")],
            "Earnings Average": 1.35,
            "Earnings Low": 1.2,
            "Earnings High": 1.5,
        },
        observed_date="2026-10-01",
        report_currency="sek",
    )

    assert row is not None
    assert row["expected_eps"] == pytest.approx(1.35)
    assert row["expected_eps_metric"] == reporting.UNVERIFIED_ESTIMATE_METRIC
    assert row["expected_eps_verified"] is False
    assert row["expected_eps_currency"] == "SEK"


@pytest.mark.parametrize("valuation_eps", [4.0, 5.25])
def test_new_eps_matches_calendar_report_before_closing_price(valuation_eps: float) -> None:
    # Synthetic report: the new quarter is known while prices still end yesterday.
    schedule = reporting._combined_schedule(
        reporting._normalise_calendar(pd.DataFrame([_calendar_row()])), pd.DataFrame()
    )
    old = _reports()
    new = old.iloc[0].to_dict()
    new.update(period_end="2026-09-30", report_period="2026-Q3",
               published_at="2026-10-08T07:50:00+02:00", effective_date="2026-10-08",
               eps_ttm=5.25, notes="report_currency=USD")
    reports = normalise_reports(pd.concat([old, pd.DataFrame([new])], ignore_index=True))
    rows = reporting._upcoming_rows(
        schedule=schedule, reports=reports, quarterly=_quarterly(),
        valuation_frames={"TEST.ST": pd.DataFrame([{
            "Date": pd.Timestamp("2026-10-07"), "EPS_TTM": valuation_eps,
        }, {"Date": pd.Timestamp("2026-10-08"), "EPS_TTM": 5.25}])},
        metadata=_metadata(), as_of=pd.Timestamp("2026-10-08"),
    )
    assert rows[0]["previous_eps_ttm"] == 4.0
    assert rows[0]["previous_eps_ttm_currency"] == "SEK"
    assert rows[0]["new_eps_ttm"] == 5.25
    assert rows[0]["new_eps_ttm_currency"] == "USD"
    assert rows[0]["next_period_end"] == "2026-09-30"
    assert rows[0]["neutral_quarter_eps"] == 1.1

    # Synthetic example: before publication only the preceding report is known.
    waiting = reporting._upcoming_rows(
        schedule=schedule, reports=old, quarterly=_quarterly(), valuation_frames={},
        metadata=_metadata(), as_of=pd.Timestamp("2026-10-07"),
    )[0]
    assert waiting["previous_eps_ttm"] == 4.0
    assert waiting["new_eps_ttm"] is None

    missing_old = reporting._upcoming_rows(
        schedule=schedule, reports=normalise_reports(pd.DataFrame([new])),
        quarterly=_quarterly(), valuation_frames={}, metadata=_metadata(),
        as_of=pd.Timestamp("2026-10-08"),
    )[0]
    assert missing_old["previous_eps_ttm"] is None
    assert missing_old["new_eps_ttm"] == 5.25

    for day in ["2026-10-01", "2026-10-09"]:
        other = reporting._combined_schedule(reporting._normalise_calendar(
            pd.DataFrame([_calendar_row(report_date_start=day, report_date_end=day)])
        ), pd.DataFrame())
        result = reporting._upcoming_rows(
            schedule=other, reports=reports, quarterly=_quarterly(),
            valuation_frames={}, metadata=_metadata(), as_of=pd.Timestamp(day),
        )
        assert result[0]["new_eps_ttm"] is None


def test_upcoming_uses_xsto_sessions_and_hides_unverified_estimate() -> None:
    schedule = reporting._combined_schedule(
        reporting._normalise_calendar(pd.DataFrame([_calendar_row()])),
        pd.DataFrame(),
    )
    valued = pd.DataFrame(
        [{"Date": pd.Timestamp("2026-10-01"), "Close": 100.0, "EPS_TTM": 4.0, "Score": 42.0}]
    )

    rows = reporting._upcoming_rows(
        schedule=schedule,
        reports=_reports(),
        quarterly=_quarterly(),
        valuation_frames={"TEST.ST": valued},
        metadata=_metadata(),
        as_of=pd.Timestamp("2026-10-01"),
    )

    assert len(rows) == 1
    assert rows[0]["trading_days_to_report"] == 5
    assert rows[0]["neutral_quarter_eps"] == pytest.approx(1.1)
    assert rows[0]["neutral_reference_period"] == "2025-09-30"
    assert rows[0]["expected_eps"] is None
    assert rows[0]["unverified_estimate_available"] is True
    assert rows[0]["estimate_status"] == "unverified_definition"


def test_verified_diluted_estimate_may_be_displayed() -> None:
    schedule = reporting._combined_schedule(
        reporting._normalise_calendar(
            pd.DataFrame(
                [
                    _calendar_row(
                        expected_eps_metric=DILUTED_METRIC,
                        expected_eps_verified=True,
                    )
                ]
            )
        ),
        pd.DataFrame(),
    )
    valued = pd.DataFrame(
        [{"Date": pd.Timestamp("2026-10-01"), "Close": 100.0, "EPS_TTM": 4.0, "Score": 42.0}]
    )

    rows = reporting._upcoming_rows(
        schedule=schedule,
        reports=_reports(),
        quarterly=_quarterly(),
        valuation_frames={"TEST.ST": valued},
        metadata=_metadata(),
        as_of=pd.Timestamp("2026-10-01"),
    )

    assert rows[0]["expected_eps"] == pytest.approx(1.35)
    assert rows[0]["estimate_status"] == "verified_comparable"


def test_recent_report_shows_actual_before_after_change() -> None:
    reports = normalise_reports(
        pd.DataFrame(
            [
                {
                    "ticker": "TEST.ST",
                    "period_end": "2026-06-30",
                    "report_period": "2026-Q2",
                    "published_at": "2026-09-01T20:00:00Z",
                    "effective_date": "2026-09-02",
                    "eps_ttm": 4.5,
                    "source": "Bolagets rapport",
                    "verified": True,
                    "verified_at": "2026-09-02T08:00:00Z",
                    "notes": "report_currency=SEK",
                }
            ]
        )
    )
    quarterly = pd.DataFrame(
        [
            {"ticker": "TEST.ST", "period_end": "2025-06-30", "observed_date": "2025-07-20", "metric": DILUTED_METRIC, "eps": 0.8, "eps_currency": "SEK"},
            {"ticker": "TEST.ST", "period_end": "2026-06-30", "observed_date": "2026-09-02", "metric": DILUTED_METRIC, "eps": 1.3, "eps_currency": "SEK"},
        ]
    )
    valued = pd.DataFrame(
        [
            {"Date": "2026-09-01", "Close": 100.0, "EPS_TTM": 4.0, "Score": 50.0},
            {"Date": "2026-09-02", "Close": 104.0, "EPS_TTM": 4.5, "Score": 44.0},
            {"Date": "2026-09-10", "Close": 105.0, "EPS_TTM": 4.5, "Score": 43.0},
        ]
    )

    rows = reporting._recent_rows(
        reports=reports,
        quarterly=quarterly,
        valuation_frames={"TEST.ST": valued},
        metadata=_metadata(),
        as_of=pd.Timestamp("2026-09-10"),
    )

    assert len(rows) == 1
    assert rows[0]["reported_quarter_eps"] == pytest.approx(1.3)
    assert rows[0]["prior_year_quarter_eps"] == pytest.approx(0.8)
    assert rows[0]["eps_ttm_before"] == pytest.approx(4.0)
    assert rows[0]["eps_ttm_after"] == pytest.approx(4.5)
    assert rows[0]["score_change"] == pytest.approx(-6.0)
    assert rows[0]["price_change_pct"] == pytest.approx(4.0)
    assert rows[0]["report_date"] == "2026-09-01"
    assert rows[0]["report_date_verified"] is True
    assert rows[0]["report_date_source"] == "published_at"


def test_recent_report_flags_effective_date_when_publication_date_is_missing() -> None:
    reports = normalise_reports(
        pd.DataFrame(
            [
                {
                    "ticker": "TEST.ST",
                    "period_end": "2026-06-30",
                    "report_period": "2026-Q2",
                    "published_at": None,
                    "effective_date": "2026-09-02",
                    "eps_ttm": 4.5,
                    "source": "Bolagets rapport",
                    "verified": True,
                    "verified_at": "2026-09-02T08:00:00Z",
                    "notes": "report_currency=SEK",
                }
            ]
        )
    )
    valued = pd.DataFrame(
        [
            {"Date": "2026-09-01", "Close": 100.0, "EPS_TTM": 4.0, "Score": 50.0},
            {"Date": "2026-09-02", "Close": 104.0, "EPS_TTM": 4.5, "Score": 44.0},
        ]
    )

    rows = reporting._recent_rows(
        reports=reports,
        quarterly=pd.DataFrame(),
        valuation_frames={"TEST.ST": valued},
        metadata=_metadata(),
        as_of=pd.Timestamp("2026-09-10"),
    )

    assert len(rows) == 1
    assert rows[0]["report_date"] == "2026-09-02"
    assert rows[0]["report_date_verified"] is False
    assert rows[0]["report_date_source"] == "effective_date_fallback"


def test_calendar_update_preserves_last_good_row_on_fetch_failure(tmp_path: Path, monkeypatch) -> None:
    metadata_path = tmp_path / "stocks.csv"
    _metadata().to_csv(metadata_path, index=False)
    monkeypatch.setattr(reporting, "METADATA_FILE", metadata_path)
    current_path = tmp_path / "current.csv"
    history_path = tmp_path / "history.csv"
    reporting.save_auto_report_calendar(pd.DataFrame([_calendar_row()]), current_path)
    reporting.save_auto_report_calendar(pd.DataFrame([_calendar_row()]), history_path)

    def failing_fetcher(ticker: str) -> dict[str, object]:
        raise RuntimeError(f"tillfälligt fel för {ticker}")

    result = reporting.update_report_calendar(
        workers=1,
        current_path=current_path,
        history_path=history_path,
        fetcher=failing_fetcher,
        observed_date="2026-10-02",
    )

    assert len(result) == 1
    assert result.iloc[0]["report_date_start"] == pd.Timestamp("2026-10-08")


def test_calendar_update_preserves_last_good_row_on_empty_response(tmp_path: Path, monkeypatch) -> None:
    metadata_path = tmp_path / "stocks.csv"
    _metadata().to_csv(metadata_path, index=False)
    monkeypatch.setattr(reporting, "METADATA_FILE", metadata_path)
    current_path = tmp_path / "current.csv"
    history_path = tmp_path / "history.csv"
    reporting.save_auto_report_calendar(pd.DataFrame([_calendar_row()]), current_path)

    result = reporting.update_report_calendar(
        workers=1,
        current_path=current_path,
        history_path=history_path,
        fetcher=lambda ticker: None,
        observed_date="2026-10-02",
    )

    assert len(result) == 1
    assert result.iloc[0]["report_date_start"] == pd.Timestamp("2026-10-08")


def test_borskollen_fetch_saves_only_exact_strategy_ticker_matches(monkeypatch) -> None:
    monkeypatch.setattr(reporting, "_metadata", lambda: pd.DataFrame([
        {"ticker": "DYVOX.ST", "company": "Dynavox Group", "price_currency": "SEK", "report_currency": "SEK"}
    ]))

    class Response:
        def __init__(self, items):
            self._items = items

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": self._items}

    class Session:
        def __init__(self):
            self.headers = {}

        def get(self, url, *, params=None, timeout=None):
            items = []
            if params["date"] == "2026-10-21":
                items = [
                    {"tagTicker": "DYVOX", "tagCountry": "Sverige", "reportDate": "2026-10-21T00:00:00Z"},
                    {"tagTicker": "OTHER", "tagCountry": "Sverige", "reportDate": "2026-10-21T00:00:00Z"},
                ]
            return Response(items)

    rows = reporting._borskollen_rows(observed_date="2026-09-17", session=Session())

    assert rows["ticker"].tolist() == ["DYVOX.ST"]
    assert rows.iloc[0]["report_date_start"] == pd.Timestamp("2026-10-21")
    assert rows.iloc[0]["source"] == reporting.BORSKOLLEN_SOURCE


def test_borskollen_has_priority_over_yahoo_for_same_report() -> None:
    yahoo = _calendar_row(ticker="DYVOX.ST", report_date_start="2026-10-21", report_date_end="2026-10-21")
    independent = _calendar_row(
        ticker="DYVOX.ST",
        report_date_start="2026-10-21",
        report_date_end="2026-10-21",
        source=reporting.BORSKOLLEN_SOURCE,
        expected_eps=None,
    )
    schedule = reporting._combined_schedule(
        reporting._normalise_calendar(pd.DataFrame([yahoo, independent])),
        pd.DataFrame(),
    )

    assert len(schedule) == 1
    assert schedule.iloc[0]["source"] == reporting.BORSKOLLEN_SOURCE


def test_report_countdown_uses_stockholm_today_while_prices_keep_their_date(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(reporting, '_metadata', lambda: pd.DataFrame())
    monkeypatch.setattr(reporting, '_combined_schedule', lambda *args: pd.DataFrame())
    def upcoming(**kwargs):
        calls['upcoming'] = kwargs['as_of']
        return []
    def recent(**kwargs):
        calls['recent'] = kwargs['as_of']
        return []
    monkeypatch.setattr(reporting, '_upcoming_rows', upcoming)
    monkeypatch.setattr(reporting, '_recent_rows', recent)
    import src.report_data_status as status
    monkeypatch.setattr(status, 'report_data_status', lambda *args, **kwargs: {})
    payload = reporting.build_reports_payload(
        reports=pd.DataFrame(),
        valuation_frames={'TEST.ST': pd.DataFrame({'Date': ['2026-10-14']})},
        generated_at='2026-10-14T22:30:00Z',
        auto_calendar=pd.DataFrame(), manual_calendar=pd.DataFrame(), quarterly=pd.DataFrame(),
        output_path=tmp_path / 'reports.json',
    )
    assert calls['upcoming'] == pd.Timestamp('2026-10-15')
    assert calls['recent'] == pd.Timestamp('2026-10-14')
    assert payload['as_of_date'] == '2026-10-14'
    assert payload['calendar_as_of_date'] == '2026-10-15'
    assert '2026-12-25' not in payload['trading_sessions']
    assert '2026-10-16' in payload['trading_sessions']
