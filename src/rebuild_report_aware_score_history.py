"""Rebuild frozen valuation scores without leaking unpublished reports.

For every report date, the report's EPS is inserted at its period end in the
calculation state.  Scores from that state are published only from the report
date until the next report date.  Repeating that process chronologically keeps
the pre-report history frozen while preserving TradingView's period-end state.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from joblib import Parallel, delayed

from .config import HISTORY_START_DATE
from .fetch_data import BASE_DATA_FILE, UPDATES_FILE, load_price_history
from .fundamentals import TV_PERIOD_END_STATE, attach_eps_ttm, load_reports, verified_reports
from .fx import load_fx_history, load_stock_currencies
from .model_data import ensure_gbm_model
from .score_history import SCORE_HISTORY_COLUMNS, SCORE_HISTORY_FILE, normalise_score_history, save_score_history
from .valuation import GBMModel, calculate_valuation


def _valuation_prices(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "ma200": "MA200",
        }
    ).sort_values("Date").reset_index(drop=True)


def _rebuild_ticker_history(
    ticker: str,
    price_group: pd.DataFrame,
    ticker_reports: pd.DataFrame,
    model: GBMModel,
    metadata: pd.DataFrame,
    fx_history: pd.DataFrame,
    history_start: pd.Timestamp,
    stamp: str,
) -> pd.DataFrame:
    if ticker_reports.empty:
        return normalise_score_history(None)

    report_dates = (
        ticker_reports["effective_date"].dropna().drop_duplicates().sort_values().tolist()
    )
    valuation_prices = _valuation_prices(price_group)
    ticker_parts: list[pd.DataFrame] = []

    for report_index, report_date in enumerate(report_dates):
        report_date = pd.Timestamp(report_date).tz_localize(None).normalize()
        next_report_date = (
            pd.Timestamp(report_dates[report_index + 1]).tz_localize(None).normalize()
            if report_index + 1 < len(report_dates)
            else None
        )
        available_reports = ticker_reports.loc[
            ticker_reports["effective_date"].le(report_date)
        ].copy()
        price_slice = valuation_prices
        if next_report_date is not None:
            price_slice = price_slice.loc[price_slice["Date"].lt(next_report_date)].copy()

        working = attach_eps_ttm(
            price_slice,
            ticker,
            available_reports,
            stock_metadata=metadata,
            fx_history=fx_history,
            calculation_mode=TV_PERIOD_END_STATE,
        )
        valued = calculate_valuation(working, model=model)
        segment_start = max(history_start, report_date)
        segment = valued.loc[
            valued["Date"].ge(segment_start)
            & (valued["Date"].lt(next_report_date) if next_report_date is not None else True)
            & valued["Score"].notna(),
            ["Date", "Score"],
        ].copy()
        if not segment.empty:
            segment["ticker"] = ticker
            segment["calculation_mode"] = TV_PERIOD_END_STATE
            segment["frozen_at"] = stamp
            segment = segment.rename(columns={"Date": "date", "Score": "score"})
            ticker_parts.append(segment[SCORE_HISTORY_COLUMNS])

    if not ticker_parts:
        return normalise_score_history(None)
    return normalise_score_history(pd.concat(ticker_parts, ignore_index=True))


def rebuild_report_aware_score_history(
    prices: pd.DataFrame,
    reports: pd.DataFrame,
    model: GBMModel,
    *,
    start_date: object = HISTORY_START_DATE,
    frozen_at: str | None = None,
    show_progress: bool = False,
    workers: int = 1,
) -> pd.DataFrame:
    """Return report-aware scores for every ticker in ``prices``.

    A separate valuation state is evaluated for each report date using only
    reports known by that date.  Its scores are retained from that report date
    up to (but excluding) the next report date.
    """

    history_start = pd.Timestamp(start_date).tz_localize(None).normalize()
    stamp = frozen_at or datetime.now(ZoneInfo("Europe/Stockholm")).isoformat(timespec="seconds")
    usable_reports = verified_reports(reports)
    metadata = load_stock_currencies()
    fx_history = load_fx_history()
    jobs = []
    for ticker, price_group in prices.groupby("ticker", sort=True):
        ticker = str(ticker)
        ticker_reports = usable_reports.loc[
            usable_reports["ticker"].astype(str).eq(ticker)
        ].sort_values(["effective_date", "published_at", "period_end"])
        jobs.append((ticker, price_group.copy(), ticker_reports.copy()))

    def run_job(job: tuple[str, pd.DataFrame, pd.DataFrame]) -> pd.DataFrame:
        ticker, price_group, ticker_reports = job
        return _rebuild_ticker_history(
            ticker, price_group, ticker_reports, model, metadata, fx_history, history_start, stamp
        )

    if workers > 1:
        rebuilt = Parallel(n_jobs=workers, verbose=10 if show_progress else 0)(
            delayed(run_job)(job) for job in jobs
        )
    else:
        rebuilt = []
        for ticker_index, job in enumerate(jobs, start=1):
            rebuilt.append(run_job(job))
            if show_progress:
                print(f"[{ticker_index}/{len(jobs)}] {job[0]}", flush=True)
    rebuilt = [part for part in rebuilt if not part.empty]

    if not rebuilt:
        return normalise_score_history(None)
    return normalise_score_history(pd.concat(rebuilt, ignore_index=True))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bygg om fryst poänghistorik rapport för rapport utan framtidsläckage."
    )
    parser.add_argument("--base-file", type=Path, default=BASE_DATA_FILE)
    parser.add_argument("--updates-file", type=Path, default=UPDATES_FILE)
    parser.add_argument("--reports-file", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=SCORE_HISTORY_FILE)
    parser.add_argument(
        "--workers", type=int, default=min(8, os.cpu_count() or 1),
        help="Antal parallella tickerberäkningar.",
    )
    args = parser.parse_args()

    prices = load_price_history(args.base_file, args.updates_file)
    reports = load_reports(args.reports_file) if args.reports_file is not None else load_reports()
    model = GBMModel.load(ensure_gbm_model())
    rebuilt = rebuild_report_aware_score_history(
        prices,
        reports,
        model,
        show_progress=True,
        workers=max(1, args.workers),
    )
    save_score_history(rebuilt, args.output)
    print(
        f"Skrev {len(rebuilt)} poänger för {rebuilt['ticker'].nunique()} aktier till {args.output}."
    )


if __name__ == "__main__":
    main()
