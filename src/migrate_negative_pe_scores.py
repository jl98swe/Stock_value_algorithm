"""One-time v3.01 migration: replace only report-known negative EPS intervals.

Positive frozen scores are preserved exactly. A report-by-report rebuild avoids
using later EPS reports to change earlier scores. New daily scores remain frozen
by the existing score-history pipeline after this migration.
"""
from __future__ import annotations

import argparse
import pandas as pd

from .fetch_data import load_price_history
from .fundamentals import load_reports, verified_reports
from .model_data import ensure_gbm_model
from .rebuild_report_aware_score_history import rebuild_report_aware_score_history
from .score_history import load_score_history, merge_score_history, save_score_history
from .valuation import GBMModel


def negative_report_intervals(history: pd.DataFrame, reports: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=history.index)
    for ticker, group in verified_reports(reports).groupby("ticker"):
        group = group.sort_values(["effective_date", "published_at", "period_end"])
        group = group.drop_duplicates("effective_date", keep="last")
        rows = list(group.itertuples())
        for i, row in enumerate(rows):
            if row.eps_ttm >= 0:
                continue
            interval = history["ticker"].eq(ticker) & history["date"].ge(row.effective_date)
            if i + 1 < len(rows):
                interval &= history["date"].lt(rows[i + 1].effective_date)
            mask |= interval
    return mask


def migrate(history: pd.DataFrame, rebuilt: pd.DataFrame, reports: pd.DataFrame) -> pd.DataFrame:
    affected = negative_report_intervals(history, reports)
    return merge_score_history(history.loc[~affected], rebuilt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrera endast negativa EPS-perioder till v3.01.")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    history = load_score_history()
    reports = load_reports()
    rebuilt = rebuild_report_aware_score_history(
        load_price_history(), reports, GBMModel.load(ensure_gbm_model()),
        negative_only=True, workers=max(1, args.workers), show_progress=True,
    )
    updated = migrate(history, rebuilt, reports)
    positive = history.loc[~negative_report_intervals(history, reports)]
    check = updated.set_index(["ticker", "date"]).loc[
        pd.MultiIndex.from_frame(positive[["ticker", "date"]])
    ].reset_index()
    pd.testing.assert_frame_equal(positive.reset_index(drop=True), check[positive.columns], check_dtype=False)
    save_score_history(updated)
    print(f"Migrerade {len(rebuilt)} negativa poäng; {len(positive)} övriga poäng bevarades exakt.")


if __name__ == "__main__":
    main()
