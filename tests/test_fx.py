import pandas as pd

from src.fx import convert_values_to_currency, required_currency_pairs, yahoo_fx_ticker


def test_required_pairs_only_include_currency_mismatches():
    metadata = pd.DataFrame(
        [
            {"ticker": "AAK.ST", "price_currency": "SEK", "report_currency": "SEK"},
            {"ticker": "ABB.ST", "price_currency": "SEK", "report_currency": "USD"},
            {"ticker": "EVO.ST", "price_currency": "SEK", "report_currency": "EUR"},
        ]
    )

    assert required_currency_pairs(metadata) == [("EUR", "SEK"), ("USD", "SEK")]
    assert yahoo_fx_ticker("USD", "SEK") == "USDSEK=X"


def test_conversion_uses_previous_completed_fx_day():
    values = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-07-16", "2026-07-17", "2026-07-20"]),
            "EPS": [2.0, 2.0, 2.0],
        }
    )
    fx = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-15", "2026-07-16", "2026-07-17"]),
            "base_currency": ["USD", "USD", "USD"],
            "quote_currency": ["SEK", "SEK", "SEK"],
            "rate": [9.50, 9.60, 9.70],
            "yahoo_ticker": ["USDSEK=X"] * 3,
        }
    )

    converted = convert_values_to_currency(
        values,
        value_column="EPS",
        date_column="Date",
        base_currency="USD",
        quote_currency="SEK",
        fx_history=fx,
        output_column="EPS_SEK",
    )

    assert converted.loc[0, "FX_RATE"] == 9.50
    assert converted.loc[1, "FX_RATE"] == 9.60
    # Måndagen använder fredagens senaste avslutade valutadag.
    assert converted.loc[2, "FX_RATE"] == 9.70
    assert converted.loc[2, "EPS_SEK"] == 19.40


def test_same_currency_needs_no_fx_history():
    values = pd.DataFrame({"Date": pd.to_datetime(["2026-07-17"]), "EPS": [13.82]})

    converted = convert_values_to_currency(
        values,
        value_column="EPS",
        date_column="Date",
        base_currency="SEK",
        quote_currency="SEK",
        fx_history=pd.DataFrame(),
        output_column="EPS_SEK",
    )

    assert converted.loc[0, "FX_RATE"] == 1.0
    assert converted.loc[0, "EPS_SEK"] == 13.82
