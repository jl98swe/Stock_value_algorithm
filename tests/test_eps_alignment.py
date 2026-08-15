from __future__ import annotations

import pandas as pd

from src.align_historical_eps_to_yahoo import _reconstruct_trailing_diluted


def test_reconstruct_missing_quarter_from_next_ttm_and_diluted_quarters() -> None:
    frame = pd.DataFrame(
        [
            # Direkt TTM finns Q2 och Q4, men Q3 saknas.
            {"ticker": "TEST.ST", "metric": "trailingDilutedEPS", "as_of_date": "2025-06-30", "value": 12.92, "currency_code": "SEK"},
            {"ticker": "TEST.ST", "metric": "trailingDilutedEPS", "as_of_date": "2025-12-31", "value": 13.16, "currency_code": "SEK"},
            # TTM_Q3 = TTM_Q4 - Q4_2025 + Q4_2024 = 13.08.
            {"ticker": "TEST.ST", "metric": "quarterlyDilutedEPS", "as_of_date": "2024-12-31", "value": 3.55, "currency_code": "SEK"},
            {"ticker": "TEST.ST", "metric": "quarterlyDilutedEPS", "as_of_date": "2025-12-31", "value": 3.63, "currency_code": "SEK"},
        ]
    )

    result = _reconstruct_trailing_diluted("TEST.ST", frame)
    q3 = result.loc[result["as_of_date"] == pd.Timestamp("2025-09-30")].iloc[0]

    assert abs(float(q3["value"]) - 13.08) < 1e-12
    assert q3["currency_code"] == "SEK"
    assert q3["alignment_status"] == "yahoo_reconstructed_diluted_ttm"


def test_never_reconstruct_across_currency_mismatch() -> None:
    frame = pd.DataFrame(
        [
            {"ticker": "TEST.ST", "metric": "trailingDilutedEPS", "as_of_date": "2025-06-30", "value": 12.92, "currency_code": "SEK"},
            {"ticker": "TEST.ST", "metric": "trailingDilutedEPS", "as_of_date": "2025-12-31", "value": 13.16, "currency_code": "SEK"},
            {"ticker": "TEST.ST", "metric": "quarterlyDilutedEPS", "as_of_date": "2024-12-31", "value": 3.55, "currency_code": "USD"},
            {"ticker": "TEST.ST", "metric": "quarterlyDilutedEPS", "as_of_date": "2025-12-31", "value": 3.63, "currency_code": "SEK"},
        ]
    )

    result = _reconstruct_trailing_diluted("TEST.ST", frame)

    assert pd.Timestamp("2025-09-30") not in set(result["as_of_date"])
