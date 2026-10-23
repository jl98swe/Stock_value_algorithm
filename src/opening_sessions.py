"""Durable opening observations for next-session execution, never close scores."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .config import ROOT
from .utils import read_json, write_json_atomic

OPENINGS_FILE = ROOT / "data/prices/opening_sessions.json"


def opening_fingerprint(path: Path = OPENINGS_FILE) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def export_pending(path: Path = OPENINGS_FILE, manifests=None) -> bool:
    manifests = manifests or [ROOT / "docs/data/dashboard/index.json", ROOT / "docs/data/strategy_overviews.json"]
    fingerprint = opening_fingerprint(path)
    return any(fingerprint != read_json(target, default={}).get("meta", {}).get("opening_sessions_sha256", "")
               for target in manifests)


def ingest(cache: dict, path: Path = OPENINGS_FILE, *, now=None) -> int:
    now = pd.Timestamp(now or datetime.now(ZoneInfo("Europe/Stockholm")))
    day = pd.Timestamp(cache.get("session_date"))
    if pd.isna(day) or day.date() != now.date():
        raise ValueError("Opening snapshot must belong to today's session")
    calendar = xcals.get_calendar("XSTO")
    if not calendar.is_session(day):
        raise ValueError("Opening snapshot is not an XSTO session")
    start = calendar.session_open(day)
    output = read_json(path, default={})
    rows = output.setdefault(day.date().isoformat(), {})
    changed = 0
    for ticker, item in cache.get("stocks", {}).items():
        quote = item.get("opening") or {}
        try:
            at = pd.Timestamp(quote.get("as_of"))
            price = float(quote.get("price"))
            valid = (at.tzinfo is not None and start <= at <= start + pd.Timedelta(minutes=5)
                     and at <= now and np.isfinite(price) and price > 0
                     and quote.get("currency") == "SEK"
                     and quote.get("source") in {"Avanza", "Nasdaq"})
        except (TypeError, ValueError):
            valid = False
        if valid and ticker not in rows:
            # First validated observation wins; retries cannot move a fill.
            rows[ticker] = {**quote, "price": price}
            changed += 1
    if changed:
        write_json_atomic(path, output)
    return changed


def append_opening(frame: pd.DataFrame, ticker: str, observations: dict) -> pd.DataFrame:
    """Append only the immediate next session; EOD rows supersede it naturally."""
    if frame.empty:
        return frame
    latest = pd.Timestamp(frame["Date"].max()).normalize()
    calendar = xcals.get_calendar("XSTO", start=latest - pd.Timedelta(days=10),
                                 end=latest + pd.Timedelta(days=20))
    day = calendar.next_session(latest)
    quote = observations.get(day.date().isoformat(), {}).get(ticker)
    if not quote:
        return frame
    row = {column: np.nan for column in frame.columns}
    row.update(Date=day.tz_localize(None), Open=quote["price"], Close=quote["price"],
               Low=quote["price"], High=quote["price"], Score=np.nan,
               MA200=frame.iloc[-1].get("MA200", np.nan),
               FundamentalLock=False, LockReason="", OpeningOnly=True)
    # The engine sees the opening and gap stops; no intraday low or close score.
    return pd.concat([frame, pd.DataFrame([row])], ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(f"Saved {ingest(read_json(args.snapshot))} new opening observations")
    if export_pending():
        import os
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
                handle.write("changed=true\n")


if __name__ == "__main__":
    main()
