import json

import pandas as pd

from src.score_history import (
    apply_frozen_scores,
    load_score_history,
    save_score_history,
    seed_score_history_from_dashboard,
)


def test_existing_score_is_immutable_and_only_new_date_is_added():
    history = pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "date": "2026-08-27",
                "score": 12.3456,
                "calculation_mode": "report_date_state",
                "frozen_at": "2026-08-27T18:00:00+02:00",
            }
        ]
    )
    recalculated = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-08-27", "2026-08-28"]),
            "Score": [98.0, 54.321],
            "PriceZone": ["Övervärderad", "Neutral"],
        }
    )

    frozen, additions = apply_frozen_scores(
        recalculated,
        "TEST.ST",
        history,
        frozen_at="2026-08-28T18:00:00+02:00",
    )

    assert frozen["Score"].tolist() == [12.3456, 54.321]
    assert frozen["PriceZone"].tolist() == ["Undervärderad", "Neutral"]
    assert additions[["ticker", "date", "score"]].to_dict("records") == [
        {"ticker": "TEST.ST", "date": pd.Timestamp("2026-08-28"), "score": 54.321}
    ]


def test_dashboard_migration_preserves_published_values(tmp_path):
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "stocks": {
                    "TEST.ST": {
                        "scores": [
                            {"date": "2026-08-27", "value": 10.1234},
                            {"date": "2026-08-28", "value": 20.5678},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    seeded = seed_score_history_from_dashboard(
        dashboard,
        frozen_at="2026-08-29T12:00:00+02:00",
    )

    assert seeded["score"].tolist() == [10.1234, 20.5678]
    assert seeded["calculation_mode"].unique().tolist() == ["report_date_state"]


def test_score_history_roundtrip_is_unique_and_stable(tmp_path):
    target = tmp_path / "valuation_score_history.csv"
    frame = pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "date": "2026-08-28",
                "score": 86.53901234567,
                "calculation_mode": "tv_state",
                "frozen_at": "2026-08-28T18:00:00+02:00",
            }
        ]
    )

    save_score_history(frame, target)
    loaded = load_score_history(target)

    assert loaded.iloc[0]["score"] == 86.5390123457
    assert loaded.iloc[0]["date"] == pd.Timestamp("2026-08-28")
