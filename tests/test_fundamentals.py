import pandas as pd

from src.fundamentals import attach_eps_ttm, normalise_reports, verified_reports


def test_eps_is_never_used_before_effective_date():
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20"]
            ),
            "Close": [100.0, 101.0, 102.0, 103.0],
        }
    )
    reports = pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "period_end": "2026-06-30",
                "report_period": "2026-Q2",
                "published_at": "2026-07-17T07:00:00+02:00",
                "effective_date": "2026-07-17",
                "eps_ttm": 10.0,
                "source": "test",
                "verified": True,
                "verified_at": "2026-07-17T07:30:00+02:00",
                "notes": "",
            }
        ]
    )

    mapped = attach_eps_ttm(prices, "TEST.ST", normalise_reports(reports))

    assert pd.isna(mapped.loc[0, "EPS_TTM"])
    assert pd.isna(mapped.loc[1, "EPS_TTM"])
    assert mapped.loc[2, "EPS_TTM"] == 10.0
    assert mapped.loc[3, "EPS_TTM"] == 10.0


def test_unverified_eps_is_excluded():
    reports = pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "period_end": "2026-06-30",
                "report_period": "2026-Q2",
                "published_at": "2026-07-17T07:00:00+02:00",
                "effective_date": "2026-07-17",
                "eps_ttm": 10.0,
                "source": "test",
                "verified": False,
                "verified_at": "",
                "notes": "",
            }
        ]
    )

    assert verified_reports(normalise_reports(reports)).empty
