"""News inbox, manual reviews, report calendar and trading locks.

The module deliberately does *not* classify article text.  A source may mark an
item as regulatory, which can trigger a conservative temporary lock, but only a
manual review decides whether the item is a profit warning, reverse profit
warning, preliminary result, report release, or not material.
"""

from __future__ import annotations

import hashlib
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ROOT
from .utils import read_json


MATERIAL_CLASSIFICATIONS = {
    "negative_profit_warning",
    "positive_profit_warning",
    "preliminary_results",
    "report_release",
}


def stable_event_id(ticker: str, link: str, published_at: str, title: str) -> str:
    raw = "|".join((ticker, link, published_at, title)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def load_news(ticker: str) -> list[dict[str, Any]]:
    path = ROOT / "data/raw/news" / f"{ticker}.json"
    items = read_json(path, default=[])
    if isinstance(items, dict):
        items = items.get("items", [])
    result: list[dict[str, Any]] = []
    for item in items or []:
        entry = dict(item)
        entry.setdefault("ticker", ticker)
        entry.setdefault(
            "event_id",
            stable_event_id(
                ticker,
                str(entry.get("link", "")),
                str(entry.get("published_at", "")),
                str(entry.get("title", "")),
            ),
        )
        entry.setdefault("is_regulatory", False)
        entry.setdefault("source", "Okänd källa")
        entry.setdefault("categories", [])
        result.append(entry)
    return sorted(result, key=lambda item: str(item.get("published_at", "")), reverse=True)


def load_reviews(path: str | Path = "data/manual/event_reviews.json") -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = ROOT / file_path
    data = read_json(file_path, default=[])
    return data if isinstance(data, list) else data.get("reviews", [])


def review_map(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("event_id")): item for item in reviews if item.get("event_id")}


def load_report_calendar(path: str | Path = "data/manual/report_calendar.csv") -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = ROOT / file_path
    columns = ["ticker", "report_period", "scheduled_at", "lock_from_date", "source", "url", "verified"]
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(file_path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    frame["scheduled_at"] = pd.to_datetime(frame["scheduled_at"], errors="coerce", utc=True)
    frame["lock_from_date"] = pd.to_datetime(frame["lock_from_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame["verified"] = frame["verified"].astype(str).str.lower().isin(("true", "1", "yes", "ja"))
    return frame[columns]


def _next_verified_report_effective_date(
    reports: pd.DataFrame,
    ticker: str,
    after: pd.Timestamp,
) -> pd.Timestamp | pd.NaT:
    subset = reports.loc[
        (reports["ticker"] == ticker)
        & reports["verified"]
        & reports["published_at"].notna()
        & (reports["published_at"] > after)
        & reports["effective_date"].notna()
    ].sort_values("effective_date")
    return subset.iloc[0]["effective_date"] if not subset.empty else pd.NaT


def enrich_news(
    ticker: str,
    news_items: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del ticker  # kept in the public signature for readability at call sites
    lookup = review_map(reviews)
    enriched: list[dict[str, Any]] = []
    for item in news_items:
        entry = dict(item)
        review = lookup.get(str(entry.get("event_id")))
        if review:
            entry["review"] = review
            entry["review_status"] = "reviewed"
            entry["classification"] = review.get("classification", "other")
            entry["lock_action"] = review.get("lock_action", "none")
            entry["review_note"] = review.get("note", "")
            entry["reviewed_at"] = review.get("reviewed_at")
        else:
            entry["review"] = None
            entry["review_status"] = "unreviewed"
            entry["classification"] = "unreviewed"
            entry["lock_action"] = "none"
            entry["review_note"] = ""
            entry["reviewed_at"] = None
        enriched.append(entry)
    return enriched


def _local_day(value: Any, timezone: str) -> pd.Timestamp | pd.NaT:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return pd.NaT
    return pd.Timestamp(timestamp.tz_convert(timezone).date())


def _clock(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":", 1))
    return time(hour, minute)


def _calendar_lock_start(
    row: pd.Series,
    dates: pd.DatetimeIndex,
    *,
    timezone: str,
    market_close_time: str,
) -> pd.Timestamp | pd.NaT:
    """Return the close whose next-open order could cross a scheduled report.

    An explicit ``lock_from_date`` always wins.  Otherwise, a report scheduled
    before that day's market close starts the lock at the previous observed
    trading session.  A release after market close starts the lock on that same
    trading day.  This prevents a stale-EPS signal from being generated at a
    close immediately before the market first prices the report.
    """

    explicit = row.get("lock_from_date")
    if not pd.isna(explicit):
        return pd.Timestamp(explicit).normalize()

    scheduled = row.get("scheduled_at")
    if pd.isna(scheduled) or dates.empty:
        return pd.NaT
    local = pd.Timestamp(scheduled).tz_convert(timezone)
    calendar_day = pd.Timestamp(local.date())

    prior = dates[dates < calendar_day]
    same_or_prior = dates[dates <= calendar_day]
    if local.time() <= _clock(market_close_time):
        return prior[-1] if len(prior) else (same_or_prior[-1] if len(same_or_prior) else dates[0])
    return same_or_prior[-1] if len(same_or_prior) else dates[0]


def build_lock_series(
    trading_dates: pd.Series,
    ticker: str,
    news_items: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    reports: pd.DataFrame,
    report_calendar: pd.DataFrame,
    *,
    lock_on_unreviewed_regulatory_news: bool = True,
    lock_on_unreviewed_nonregulatory_news: bool = False,
    timezone: str = "Europe/Stockholm",
    market_close_time: str = "17:30",
) -> pd.DataFrame:
    """Create a daily lock flag without automatically interpreting article text.

    Unreviewed items only lock when source metadata says they are regulatory (or
    the stricter non-regulatory setting is enabled). Reviewed profit warnings,
    preliminary results and report releases lock until a later verified report
    becomes effective. Items reviewed as non-material stop locking on the local
    review date.
    """

    dates = pd.DatetimeIndex(pd.to_datetime(trading_dates)).tz_localize(None).normalize()
    output = pd.DataFrame(
        {
            "Date": dates,
            "FundamentalLock": False,
            "LockReason": "",
            "LockEventIds": [[] for _ in dates],
        }
    )
    lookup = review_map(reviews)
    intervals: list[tuple[pd.Timestamp, pd.Timestamp | None, str, str]] = []

    for item in news_items:
        event_id = str(item.get("event_id"))
        published = pd.to_datetime(item.get("published_at"), errors="coerce", utc=True)
        if pd.isna(published):
            continue
        start = _local_day(published, timezone)
        review = lookup.get(event_id)
        regulatory = bool(item.get("is_regulatory", False))

        if review is None:
            should_lock = (regulatory and lock_on_unreviewed_regulatory_news) or (
                (not regulatory) and lock_on_unreviewed_nonregulatory_news
            )
            if should_lock:
                intervals.append((start, None, "Ogranskad bolagsnyhet", event_id))
            continue

        classification = str(review.get("classification", "other"))
        action = str(review.get("lock_action", "none"))
        reviewed_at = pd.to_datetime(review.get("reviewed_at"), errors="coerce", utc=True)
        if classification in {"not_material", "other"} or action == "release":
            if regulatory and lock_on_unreviewed_regulatory_news and not pd.isna(reviewed_at):
                end = _local_day(reviewed_at, timezone)
                intervals.append((start, end, "Inväntade manuell granskning", event_id))
            continue

        if action == "lock_until_verified_report" or classification in MATERIAL_CLASSIFICATIONS:
            end = _next_verified_report_effective_date(reports, ticker, published)
            reason_names = {
                "negative_profit_warning": "Negativ vinstvarning – väntar på verifierad EPS",
                "positive_profit_warning": "Omvänd vinstvarning – väntar på verifierad EPS",
                "preliminary_results": "Preliminärt resultat – väntar på verifierad EPS",
                "report_release": "Rapport publicerad – väntar på verifierad EPS",
            }
            intervals.append(
                (
                    start,
                    None if pd.isna(end) else pd.Timestamp(end),
                    reason_names.get(classification, "Fundamentaldata väntar på verifiering"),
                    event_id,
                )
            )

    calendar = report_calendar.loc[report_calendar["ticker"] == ticker]
    for _, row in calendar.iterrows():
        start = _calendar_lock_start(
            row,
            dates,
            timezone=timezone,
            market_close_time=market_close_time,
        )
        if pd.isna(start):
            continue
        scheduled = row.get("scheduled_at")
        end = pd.NaT
        if not pd.isna(scheduled):
            end = _next_verified_report_effective_date(reports, ticker, scheduled)
        intervals.append(
            (
                pd.Timestamp(start),
                None if pd.isna(end) else pd.Timestamp(end),
                f"Rapport {row.get('report_period', '')} väntas – EPS måste verifieras",
                f"calendar:{row.get('report_period', '')}",
            )
        )

    reasons_by_index: list[list[str]] = [[] for _ in dates]
    ids_by_index: list[list[str]] = [[] for _ in dates]
    for start, end, reason, event_id in intervals:
        mask = dates >= pd.Timestamp(start)
        if end is not None:
            mask &= dates < pd.Timestamp(end)
        for index, value in enumerate(mask):
            if bool(value):
                reasons_by_index[index].append(reason)
                ids_by_index[index].append(event_id)

    output["FundamentalLock"] = [bool(values) for values in reasons_by_index]
    output["LockReason"] = ["; ".join(dict.fromkeys(values)) for values in reasons_by_index]
    output["LockEventIds"] = ids_by_index
    return output
