"""Append-only storage for published valuation scores.

The valuation engine may recalculate its rolling state when fundamentals are
updated. Published chart values must not be rewritten by those recalculations,
so this module freezes the first score stored for each ticker and trading day.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .valuation import price_zone

SCORE_HISTORY_FILE = ROOT / "data" / "derived" / "valuation_score_history.csv.gz"
SCORE_HISTORY_COLUMNS = ["ticker", "date", "score", "calculation_mode", "frozen_at"]
DEFAULT_CALCULATION_MODE = "report_date_state"


def empty_score_history() -> pd.DataFrame:
    return pd.DataFrame(columns=SCORE_HISTORY_COLUMNS)


def normalise_score_history(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return empty_score_history()

    result = frame.copy()
    for column in SCORE_HISTORY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    result["ticker"] = result["ticker"].astype("string").str.strip()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["score"] = pd.to_numeric(result["score"], errors="coerce")
    result["calculation_mode"] = (
        result["calculation_mode"]
        .astype("string")
        .fillna(DEFAULT_CALCULATION_MODE)
        .replace("", DEFAULT_CALCULATION_MODE)
    )
    result["frozen_at"] = result["frozen_at"].astype("string").fillna("")

    result = result.dropna(subset=["ticker", "date", "score"])
    result = result.loc[
        result["ticker"].str.len().fillna(0).gt(0)
        & np.isfinite(result["score"])
        & result["score"].between(0.0, 100.0)
    ]
    if result.duplicated(["ticker", "date"]).any():
        duplicates = result.loc[
            result.duplicated(["ticker", "date"], keep=False), ["ticker", "date"]
        ].head(10)
        raise ValueError(
            "Fryst poänghistorik innehåller dubbla ticker+date: "
            f"{duplicates.to_dict('records')}"
        )

    return result[SCORE_HISTORY_COLUMNS].sort_values(["ticker", "date"]).reset_index(drop=True)


def load_score_history(path: str | Path = SCORE_HISTORY_FILE) -> pd.DataFrame:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists() or target.stat().st_size == 0:
        return empty_score_history()
    return normalise_score_history(pd.read_csv(target))


def seed_score_history_from_dashboard(path: str | Path, *, frozen_at: str) -> pd.DataFrame:
    """Migrate the already published dashboard scores without recalculating them."""

    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return empty_score_history()
    with target.open("r", encoding="utf-8") as handle:
        dashboard = json.load(handle)

    rows: list[dict[str, object]] = []
    stocks = dashboard.get("stocks", {}) if isinstance(dashboard, dict) else {}
    if not isinstance(stocks, dict):
        return empty_score_history()
    for ticker, payload in stocks.items():
        if not isinstance(payload, dict):
            continue
        for item in payload.get("scores", []):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "ticker": str(ticker),
                    "date": item.get("date"),
                    "score": item.get("value"),
                    "calculation_mode": DEFAULT_CALCULATION_MODE,
                    "frozen_at": frozen_at,
                }
            )
    return normalise_score_history(pd.DataFrame(rows, columns=SCORE_HISTORY_COLUMNS))


def apply_frozen_scores(
    valued: pd.DataFrame,
    ticker: str,
    history: pd.DataFrame,
    *,
    frozen_at: str,
    calculation_mode: str = DEFAULT_CALCULATION_MODE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use existing published scores and return newly frozen dates separately."""

    result = valued.copy()
    if "Date" not in result.columns or "Score" not in result.columns:
        raise ValueError("Värderingsdata måste innehålla Date och Score")

    dates = pd.to_datetime(result["Date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    candidate_scores = pd.to_numeric(result["Score"], errors="coerce")
    if history is None or history.empty:
        existing = empty_score_history()
    elif "ticker" not in history.columns:
        raise ValueError("Fryst poänghistorik måste innehålla ticker")
    else:
        ticker_rows = history.loc[history["ticker"].astype(str) == str(ticker)].copy()
        existing = normalise_score_history(ticker_rows)

    # A deliberate calculation-mode migration may happen when the market is
    # closed and no newer trading day exists. Replace only that final published
    # day once; older scores remain frozen. The replacement stores the new mode,
    # so later runs return to normal append-only behaviour.
    if (
        not existing.empty
        and dates.max() <= existing["date"].max()
        and str(existing.iloc[-1]["calculation_mode"]) != str(calculation_mode)
    ):
        latest_date = existing.iloc[-1]["date"]
        existing = existing.loc[existing["date"] < latest_date].copy()
    frozen_by_date = existing.set_index("date")["score"] if not existing.empty else pd.Series(dtype=float)

    frozen_scores = dates.map(frozen_by_date)
    use_existing = frozen_scores.notna()
    result.loc[use_existing, "Score"] = frozen_scores.loc[use_existing].to_numpy(dtype=float)

    after_frozen_history = pd.Series(True, index=result.index)
    if not existing.empty:
        latest_frozen_date = existing["date"].max()
        after_frozen_history = dates.gt(latest_frozen_date)
        historical_gap = dates.le(latest_frozen_date) & ~dates.isin(frozen_by_date.index)
        result.loc[historical_gap, "Score"] = np.nan
    new_mask = (
        dates.notna()
        & candidate_scores.notna()
        & ~dates.isin(frozen_by_date.index)
        & after_frozen_history
    )
    additions = pd.DataFrame(
        {
            "ticker": str(ticker),
            "date": dates.loc[new_mask],
            "score": candidate_scores.loc[new_mask].astype(float),
            "calculation_mode": calculation_mode,
            "frozen_at": frozen_at,
        }
    )
    additions = normalise_score_history(additions)

    # Dependent display fields must follow the immutable score rather than the
    # newly recalculated candidate value.
    result["PriceZone"] = result["Score"].map(price_zone)
    return result, additions


def merge_score_history(
    history: pd.DataFrame,
    additions: pd.DataFrame,
) -> pd.DataFrame:
    """Merge additions, replacing only explicitly returned ticker/date keys."""

    existing = normalise_score_history(history)
    incoming = normalise_score_history(additions)
    if incoming.empty:
        return existing

    incoming_keys = pd.MultiIndex.from_frame(incoming[["ticker", "date"]])
    existing_keys = pd.MultiIndex.from_frame(existing[["ticker", "date"]])
    existing = existing.loc[~existing_keys.isin(incoming_keys)].copy()
    return normalise_score_history(pd.concat([existing, incoming], ignore_index=True))


def save_score_history(frame: pd.DataFrame, path: str | Path = SCORE_HISTORY_FILE) -> None:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)

    output = normalise_score_history(frame).copy()
    output["date"] = output["date"].dt.strftime("%Y-%m-%d")
    output["score"] = output["score"].round(10)
    temp = target.with_suffix(target.suffix + ".tmp")
    compression = {"method": "gzip", "mtime": 0} if target.suffix == ".gz" else None
    output.to_csv(temp, index=False, compression=compression)
    temp.replace(target)
