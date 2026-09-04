import pandas as pd

from src.fundamentals import (
    REPORT_DATE_STATE,
    TV_PERIOD_END_STATE,
    attach_eps_ttm,
    normalise_reports,
    valuation_calculation_mode,
    verified_reports,
)


def _verified_report(ticker: str = "TEST.ST", eps_ttm: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "period_end": "2026-06-30",
                "report_period": "2026-Q2",
                "published_at": "2026-07-17T07:00:00+02:00",
                "effective_date": "2026-07-17",
                "eps_ttm": eps_ttm,
                "source": "test",
                "verified": True,
                "verified_at": "2026-07-17T07:30:00+02:00",
                "notes": "",
            }
        ]
    )


def test_eps_is_never_used_before_effective_date():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20"]
            ),
            "Close": [100.0, 101.0, 102.0, 103.0],
        }
    )

    mapped = attach_eps_ttm(prices, "TEST.ST", normalise_reports(_verified_report()))

    assert pd.isna(mapped.loc[0, "EPS_TTM"])
    assert pd.isna(mapped.loc[1, "EPS_TTM"])
    assert mapped.loc[2, "EPS_TTM"] == 10.0
    assert mapped.loc[3, "EPS_TTM"] == 10.0


def test_tv_mode_uses_period_end_without_changing_report_date_mode():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-06-30", "2026-07-16", "2026-07-17"]),
            "Close": [100.0, 101.0, 102.0],
        }
    )
    reports = normalise_reports(_verified_report())

    report_date = attach_eps_ttm(
        prices,
        "TEST.ST",
        reports,
        calculation_mode=REPORT_DATE_STATE,
    )
    tv_period_end = attach_eps_ttm(
        prices,
        "TEST.ST",
        reports,
        calculation_mode=TV_PERIOD_END_STATE,
    )

    assert pd.isna(report_date.loc[0, "EPS_TTM"])
    assert pd.isna(report_date.loc[1, "EPS_TTM"])
    assert report_date.loc[2, "EPS_TTM"] == 10.0
    assert tv_period_end["EPS_TTM"].tolist() == [10.0, 10.0, 10.0]


def test_tradingview_source_activates_tv_mode_only_for_that_ticker():
    tradingview = _verified_report(ticker="TV.ST")
    tradingview.loc[0, "source"] = "TradingView / EARNINGS_PER_SHARE_DILUTED TTM"
    ordinary = _verified_report(ticker="OTHER.ST")
    reports = normalise_reports(pd.concat([tradingview, ordinary], ignore_index=True))

    assert valuation_calculation_mode("TV.ST", reports) == TV_PERIOD_END_STATE
    assert valuation_calculation_mode("OTHER.ST", reports) == REPORT_DATE_STATE


def test_unverified_eps_is_excluded():
    reports = _verified_report()
    reports.loc[0, "verified"] = False
    reports.loc[0, "verified_at"] = ""

    assert verified_reports(normalise_reports(reports)).empty


def test_report_currency_is_converted_before_pe_input():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-07-17", "2026-07-20"]),
            "Close": [200.0, 210.0],
        }
    )
    metadata = pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "price_currency": "SEK",
                "report_currency": "USD",
            }
        ]
    )
    fx = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-16", "2026-07-17"]),
            "base_currency": ["USD", "USD"],
            "quote_currency": ["SEK", "SEK"],
            "rate": [9.50, 9.60],
            "yahoo_ticker": ["USDSEK=X", "USDSEK=X"],
        }
    )

    mapped = attach_eps_ttm(
        prices,
        "TEST.ST",
        normalise_reports(_verified_report(eps_ttm=2.0)),
        stock_metadata=metadata,
        fx_history=fx,
    )

    assert mapped.loc[0, "EPS_TTM_RAW"] == 2.0
    assert mapped.loc[0, "EPS_CURRENCY"] == "USD"
    assert mapped.loc[0, "PRICE_CURRENCY"] == "SEK"
    assert mapped.loc[0, "FX_RATE"] == 9.50
    assert mapped.loc[0, "EPS_TTM"] == 19.0
    assert mapped.loc[1, "FX_RATE"] == 9.60
    assert mapped.loc[1, "EPS_TTM"] == 19.2


def test_tradingview_override_can_use_price_currency_for_one_report():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-03-31", "2026-06-30", "2026-07-01"]),
            "Close": [200.0, 210.0, 211.0],
        }
    )
    usd_report = _verified_report(ticker="TEST.ST", eps_ttm=2.0)
    usd_report.loc[0, ["period_end", "effective_date"]] = ["2026-03-31", "2026-04-17"]
    usd_report.loc[0, "report_period"] = "2026-Q1"
    usd_report.loc[0, "notes"] = "metric=trailingDilutedEPS; report_currency=USD"

    tv_report = _verified_report(ticker="TEST.ST", eps_ttm=26.4067)
    tv_report.loc[0, ["period_end", "effective_date"]] = ["2026-06-30", "2026-07-16"]
    tv_report.loc[0, "source"] = "TradingView / EARNINGS_PER_SHARE_DILUTED TTM"
    tv_report.loc[0, "notes"] = "metric=EARNINGS_PER_SHARE_DILUTED TTM; report_currency=SEK"
    reports = normalise_reports(pd.concat([usd_report, tv_report], ignore_index=True))
    metadata = pd.DataFrame(
        [{"ticker": "TEST.ST", "price_currency": "SEK", "report_currency": "USD"}]
    )
    fx = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-03-30", "2026-06-29", "2026-06-30"]),
            "base_currency": ["USD", "USD", "USD"],
            "quote_currency": ["SEK", "SEK", "SEK"],
            "rate": [10.0, 9.5, 9.6],
            "yahoo_ticker": ["USDSEK=X", "USDSEK=X", "USDSEK=X"],
        }
    )

    mapped = attach_eps_ttm(
        prices,
        "TEST.ST",
        reports,
        stock_metadata=metadata,
        fx_history=fx,
        calculation_mode=TV_PERIOD_END_STATE,
    )

    assert pd.isna(mapped.loc[0, "EPS_TTM"])
    assert mapped.loc[1, "EPS_CURRENCY"] == "SEK"
    assert mapped.loc[1, "FX_RATE"] == 1.0
    assert mapped.loc[1, "EPS_TTM"] == 26.4067
    assert mapped.loc[2, "EPS_TTM"] == 26.4067


def test_tradingview_period_end_is_usable_when_report_date_is_unknown():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2018-09-28", "2018-10-01"]),
            "Close": [100.0, 101.0],
        }
    )
    report = _verified_report(ticker="TV.ST", eps_ttm=5.0)
    report.loc[0, ["period_end", "effective_date"]] = ["2018-09-30", pd.NaT]
    report.loc[0, "report_period"] = "2018-Q3"
    report.loc[0, "source"] = "TradingView / EARNINGS_PER_SHARE_DILUTED TTM"
    report.loc[0, "notes"] = "report_currency=SEK"
    reports = normalise_reports(report)

    assert len(verified_reports(reports)) == 1
    mapped = attach_eps_ttm(
        prices,
        "TV.ST",
        reports,
        calculation_mode=TV_PERIOD_END_STATE,
    )

    assert pd.isna(mapped.loc[0, "EPS_TTM"])
    assert mapped.loc[1, "EPS_TTM"] == 5.0


def test_current_tradingview_value_applies_when_observed_before_period_end():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-09-03", "2026-09-04"]),
            "Close": [100.0, 101.0],
        }
    )
    report = _verified_report(ticker="TV.ST", eps_ttm=6.0)
    report.loc[0, ["period_end", "effective_date"]] = ["2026-09-30", "2026-09-04"]
    report.loc[0, "report_period"] = "2026-Q3"
    report.loc[0, "source"] = "TradingView / EARNINGS_PER_SHARE_DILUTED TTM"
    report.loc[0, "notes"] = "report_currency=SEK; report_date_status=observed_in_export"
    reports = normalise_reports(report)

    mapped = attach_eps_ttm(
        prices,
        "TV.ST",
        reports,
        calculation_mode=TV_PERIOD_END_STATE,
    )

    assert pd.isna(mapped.loc[0, "EPS_TTM"])
    assert mapped.loc[1, "EPS_TTM"] == 6.0
