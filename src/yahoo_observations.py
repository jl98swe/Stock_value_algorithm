"""Append fetched EPS observations before model selection or manual priority."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from .config import ROOT

ARCHIVE_DIR = ROOT / "data/earnings/yahoo_observations"


def archive_eps(frame: pd.DataFrame, collection: str, directory: Path | None = None) -> None:
    if frame.empty:
        return
    target = (directory or ARCHIVE_DIR) / f"{collection}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    records = frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
    payload = {"fetched_at": datetime.now(timezone.utc).isoformat(), "records": records}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                default=lambda value: value.isoformat()) + "\n")


def seed_history(root: Path = ROOT) -> None:
    directory = root / "data/earnings/yahoo_observations"
    for relative in ["data/earnings/earnings_initial.csv", "data/earnings/earnings_updates.csv",
                     "data/earnings/quarterly_eps.csv", "data/derived/yahoo_trailing_eps_timeseries_audit.csv"]:
        path = root / relative
        collection = "baseline_" + path.stem
        if path.exists() and not (directory / f"{collection}.jsonl").exists():
            frame = pd.read_csv(path)
            if "source" in frame:
                frame = frame.loc[frame["source"].astype(str).str.contains("Yahoo", case=False)]
            archive_eps(frame, collection, directory)


if __name__ == "__main__":
    seed_history()
