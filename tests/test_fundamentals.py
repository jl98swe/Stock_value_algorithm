import pandas as pd

from src.fundamentals import attach_eps_ttm, normalise_reports, verified_reports


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
