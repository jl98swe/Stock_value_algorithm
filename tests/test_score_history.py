import json

import pandas as pd

from src.pipeline import SCORE_HISTORY_BOOTSTRAP_CUTOFFS, _score_recalculation_cutoffs
from src.score_history import (
    apply_frozen_scores,
    load_score_history,
    merge_score_history,
    save_score_history,
    seed_score_history_from_dashboard,
)


def test_existing_scores_are_immutable_and_only_new_days_are_added():
    history = pd.DataFrame({
        "ticker": ["TEST.ST", "TEST.ST"],
        "date": ["2026-09-02", "2026-09-03"],
        "score": [61.34, 99.41],
        "calculation_mode": ["tv_period_end_state"] * 2,
        "frozen_at": ["old"] * 2,
    })
    recalculated = pd.DataFrame({
        "Date": pd.to_datetime(["2026-09-02", "2026-09-03", "2026-09-04"]),
        "Score": [5.0, 6.0, 66.75],
    })
    result, additions = apply_frozen_scores(
        recalculated, "TEST.ST", history, frozen_at="new",
        calculation_mode="tv_period_end_state",
    )
    assert result["Score"].tolist() == [61.34, 99.41, 66.75]
    assert additions[["date", "score"]].to_dict("records") == [
        {"date": pd.Timestamp("2026-09-04"), "score": 66.75}
    ]


def test_explicit_report_day_rebase_keeps_earlier_history():
    history = pd.DataFrame({
        "ticker": ["CLAS-B.ST"] * 3,
        "date": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]),
        "score": [84.13, 61.34, 68.71],
        "calculation_mode": ["report_date_state"] * 3,
        "frozen_at": ["old"] * 3,
    })
    recalculated = pd.DataFrame({
        "Date": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]),
        "Score": [1.0, 2.0, 99.41],
    })
    result, additions = apply_frozen_scores(
        recalculated, "CLAS-B.ST", history, frozen_at="repair",
        calculation_mode="tv_period_end_state", recalculate_from="2026-09-03",
    )
    merged = merge_score_history(history, additions)
    assert result["Score"].tolist() == [84.13, 61.34, 99.41]
    assert merged["score"].tolist() == [84.13, 61.34, 99.41]


def test_dashboard_seed_and_gzip_roundtrip_are_stable(tmp_path):
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(json.dumps({
        "stocks": {"TEST.ST": {"scores": [{"date": "2026-09-02", "value": 12.5}]}}
    }), encoding="utf-8")
    seeded = seed_score_history_from_dashboard(dashboard, frozen_at="migration")
    target = tmp_path / "scores.csv.gz"
    save_score_history(seeded, target)
    first = target.read_bytes()
    save_score_history(load_score_history(target), target)
    assert target.read_bytes() == first


def test_score_recalculation_cutoff_parser():
    assert _score_recalculation_cutoffs(["CLAS-B.ST=2026-09-03"]) == {
        "CLAS-B.ST": "2026-09-03"
    }


def test_bootstrap_repairs_only_reports_affected_by_the_regression():
    assert SCORE_HISTORY_BOOTSTRAP_CUTOFFS == {
        "CLAS-B.ST": "2026-09-03",
        "SECT-B.ST": "2026-09-04",
        "SYSR.ST": "2026-09-04",
    }
