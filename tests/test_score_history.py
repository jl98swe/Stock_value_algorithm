import json

import pandas as pd

from src.score_history import (
    apply_frozen_scores,
    load_score_history,
    merge_score_history,
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
            "Date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28"]),
            "Score": [77.0, 98.0, 54.321],
            "PriceZone": ["Relativt dyr", "Övervärderad", "Neutral"],
        }
    )

    frozen, additions = apply_frozen_scores(
        recalculated,
        "TEST.ST",
        history,
        frozen_at="2026-08-28T18:00:00+02:00",
        calculation_mode="tv_period_end_state",
    )

    assert pd.isna(frozen.loc[0, "Score"])
    assert frozen.loc[1:, "Score"].tolist() == [12.3456, 54.321]
    assert frozen["PriceZone"].tolist() == ["N/A", "Undervärderad", "Neutral"]
    assert additions[["ticker", "date", "score"]].to_dict("records") == [
        {"ticker": "TEST.ST", "date": pd.Timestamp("2026-08-28"), "score": 54.321}
    ]
    assert additions.iloc[0]["calculation_mode"] == "tv_period_end_state"


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


def test_gzip_score_history_is_byte_stable(tmp_path):
    target = tmp_path / "valuation_score_history.csv.gz"
    frame = pd.DataFrame(
        [
            {
                "ticker": "TEST.ST",
                "date": "2026-08-28",
                "score": 86.539021,
                "calculation_mode": "tv_period_end_state",
                "frozen_at": "2026-08-29T12:00:00+02:00",
            }
        ]
    )

    save_score_history(frame, target)
    first = target.read_bytes()
    save_score_history(frame, target)

    assert target.read_bytes() == first


def test_mode_change_replaces_only_latest_frozen_score_without_new_market_day():
    valued = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28"]),
            "Score": [10.0, 20.0, 43.1413822598],
        }
    )
    history = pd.DataFrame(
        {
            "ticker": ["ABB.ST", "ABB.ST", "ABB.ST"],
            "date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28"]),
            "score": [11.0, 21.0, 46.7469],
            "calculation_mode": ["report_date_state"] * 3,
            "frozen_at": ["old"] * 3,
        }
    )

    result, additions = apply_frozen_scores(
        valued,
        "ABB.ST",
        history,
        frozen_at="new",
        calculation_mode="tv_period_end_state",
    )

    assert result["Score"].tolist() == [11.0, 21.0, 43.1413822598]
    assert additions[["ticker", "score", "calculation_mode"]].to_dict("records") == [
        {
            "ticker": "ABB.ST",
            "score": 43.1413822598,
            "calculation_mode": "tv_period_end_state",
        }
    ]

    merged = merge_score_history(history, additions)
    latest = merged.loc[merged["ticker"] == "ABB.ST"].iloc[-1]
    assert len(merged.loc[merged["ticker"] == "ABB.ST"]) == 3
    assert latest["date"] == pd.Timestamp("2026-08-28")
    assert latest["score"] == 43.1413822598
    assert latest["calculation_mode"] == "tv_period_end_state"


def test_earlier_verified_history_rebuilds_the_ticker_once():
    valued = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2025-12-30", "2026-08-27", "2026-08-28"]),
            "Score": [10.0, 20.0, 30.0],
        }
    )
    history = pd.DataFrame(
        {
            "ticker": ["ABB.ST", "ABB.ST"],
            "date": pd.to_datetime(["2026-08-27", "2026-08-28"]),
            "score": [91.0, 92.0],
            "calculation_mode": ["tv_period_end_state"] * 2,
            "frozen_at": ["old"] * 2,
        }
    )

    result, additions = apply_frozen_scores(
        valued,
        "ABB.ST",
        history,
        frozen_at="new",
        calculation_mode="tv_period_end_state",
    )

    assert result["Score"].tolist() == [10.0, 20.0, 30.0]
    assert additions["score"].tolist() == [10.0, 20.0, 30.0]
    merged = merge_score_history(history, additions)
    assert merged["score"].tolist() == [10.0, 20.0, 30.0]

    _, second_additions = apply_frozen_scores(
        valued,
        "ABB.ST",
        merged,
        frozen_at="later",
        calculation_mode="tv_period_end_state",
    )
    assert second_additions.empty
