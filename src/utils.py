from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ROOT


def normalize_date_column(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "Date" not in result.columns and "date" in result.columns:
        result = result.rename(columns={"date": "Date"})
    if "Date" in result.columns:
        result["Date"] = pd.to_datetime(result["Date"], errors="coerce").dt.tz_localize(None)
        result = result.sort_values("Date").reset_index(drop=True)
    return result


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def write_json_atomic(path: str | Path, payload: Any, *, pretty: bool = False) -> None:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, allow_nan=False),
        encoding="utf-8",
    )
    temp.replace(target)
