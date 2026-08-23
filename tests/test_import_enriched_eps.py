from __future__ import annotations

import pandas as pd

from src.import_enriched_eps import _overlapping_auto_mask


def test_auto_row_with_stale_report_period_is_replaced() -> None:
    existing = pd.DataFrame(
        [
            {
                "ticker": "ATT.ST",
                "period_end": "2026-06-30",
                "report_period": "2026-Q1",
                "notes": "yahoo_eps_auto_v1; stale mapping",
            },
            {
                "ticker": "ATT.ST",
                "period_end": "2026-06-30",
                "report_period": "YAHOO-2026-06-30",
                "notes": "yahoo_eps_auto_v1; genuine future period",
            },
            {
                "ticker": "ATT.ST",
                "period_end": "2026-06-30",
                "report_period": "2026-Q1",
                "notes": "manual verified report",
            },
        ]
    )
    generated = pd.DataFrame(
        [
            {
                "ticker": "ATT.ST",
                "period_end": "2026-03-31",
                "report_period": "2026-Q1",
            }
        ]
    )

    mask = _overlapping_auto_mask(existing, generated)

    assert mask.tolist() == [True, False, False]


def test_auto_row_with_matching_period_end_is_replaced() -> None:
    existing = pd.DataFrame(
        [
            {
                "ticker": "ATT.ST",
                "period_end": "2026-03-31",
                "report_period": "YAHOO-2026-03-31",
                "notes": "yahoo_eps_auto_v1",
            }
        ]
    )
    generated = pd.DataFrame(
        [
            {
                "ticker": "ATT.ST",
                "period_end": "2026-03-31",
                "report_period": "2026-Q1",
            }
        ]
    )

    assert _overlapping_auto_mask(existing, generated).tolist() == [True]
