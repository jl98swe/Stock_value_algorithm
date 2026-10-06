"""Fetch Nasdaq's OMXSGI gross-return series from its daily FRED release."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import exchange_calendars as xcals

from .config import HISTORY_START_DATE, ROOT
from .fetch_data import last_completed_session
from .utils import read_json, write_json_atomic

INDEX_FILE = ROOT / "docs" / "data" / "benchmarks" / "omxsgi.json"
SOURCE_URL = "https://fred.stlouisfed.org/series/NASDAQOMXSGI"
DOWNLOAD_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQOMXSGI"


def parse_index_csv(text: str, cutoff: str) -> list[dict]:
    frame = pd.read_csv(io.StringIO(text))
    if not {"observation_date", "NASDAQOMXSGI"}.issubset(frame):
        raise ValueError("OMXSGI: oväntade kolumner i FRED-svaret.")
    frame["date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["NASDAQOMXSGI"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"])
    frame = frame.loc[frame["date"].between(HISTORY_START_DATE, cutoff) & frame["close"].gt(0)]
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    if not frame.empty:
        sessions = xcals.get_calendar("XSTO", start=HISTORY_START_DATE, end=cutoff).sessions
        sessions = sessions.tz_localize(None) if sessions.tz is not None else sessions
        frame = frame.loc[frame["date"].isin(sessions)]
    if frame.empty:
        raise ValueError("OMXSGI: svaret innehåller ingen användbar historik.")
    return [{"date": row.date.date().isoformat(), "close": float(row.close)} for row in frame.itertuples()]


def update_index(path: Path = INDEX_FILE) -> dict:
    """Retain the last successful export on network/parse failure; never publish zeros."""
    old = read_json(path, default={})
    try:
        cutoff = last_completed_session().date().isoformat()
        with urlopen(DOWNLOAD_URL, timeout=30) as response:
            points = parse_index_csv(response.read().decode("utf-8-sig"), cutoff)
        if old.get("candles") and points[-1]["date"] < old["candles"][-1]["date"]:
            raise ValueError("OMXSGI: svaret är äldre än det sparade underlaget.")
        by_day = {p["date"]: p for p in old.get("candles", [])}
        by_day.update({p["date"]: p for p in points})
        sessions = {d.date().isoformat() for d in xcals.get_calendar("XSTO", start=HISTORY_START_DATE, end=cutoff).sessions}
        points = [by_day[day] for day in sorted(by_day) if day in sessions]
        payload = {"meta": {"name": "OMXSGI", "source": "Nasdaq via FRED", "source_url": SOURCE_URL,
                            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "start_date": points[0]["date"], "end_date": points[-1]["date"],
                            "return_type": "gross_total_return"}, "candles": points}
        write_json_atomic(path, payload)
        print(f"OMXSGI: {len(points)} observationer, till och med {points[-1]['date']}.")
        return payload
    except (OSError, ValueError) as error:
        if not old.get("candles"):
            raise
        print(f"OMXSGI: behåller tidigare underlag ({old['candles'][-1]['date']}): {error}")
        return old


if __name__ == "__main__":
    update_index()
