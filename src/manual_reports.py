from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import load_reports, normalise_reports
from .utils import write_json_atomic

AUDIT_FILE = ROOT / "data" / "manual" / "report_submissions.csv"
WEB_FILE = ROOT / "docs" / "data" / "manual_reports.json"
AUDIT_COLUMNS = [
    "submission_id",
    "ticker",
    "report_period",
    "period_end",
    "published_at",
    "effective_date",
    "input_metric",
    "input_eps",
    "result_eps_ttm",
    "eps_currency",
    "source",
    "notes",
    "submitted_at",
]


def load_manual_submissions(path: str | Path = AUDIT_FILE) -> pd.DataFrame:
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    frame = pd.read_csv(target, dtype=str).fillna("")
    for column in AUDIT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[AUDIT_COLUMNS]


def append_manual_submission(
    *,
    ticker: str,
    report_period: str,
    period_end: str,
    published_at: str,
    effective_date: str,
    input_metric: str,
    input_eps: float,
    result_eps_ttm: float,
    eps_currency: str,
    source: str,
    notes: str,
    path: str | Path = AUDIT_FILE,
) -> pd.DataFrame:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    submitted_at = datetime.now(timezone.utc).isoformat()
    identity = json.dumps(
        [ticker, report_period, input_metric, input_eps, submitted_at],
        ensure_ascii=False,
    )
    row = {
        "submission_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "ticker": ticker.strip(),
        "report_period": report_period.strip(),
        "period_end": period_end,
        "published_at": published_at,
        "effective_date": effective_date,
        "input_metric": input_metric,
        "input_eps": str(float(input_eps)),
        "result_eps_ttm": str(float(result_eps_ttm)),
        "eps_currency": eps_currency.strip().upper(),
        "source": source.strip(),
        "notes": notes.strip(),
        "submitted_at": submitted_at,
    }
    combined = pd.concat([load_manual_submissions(target), pd.DataFrame([row])], ignore_index=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    combined[AUDIT_COLUMNS].to_csv(temp, index=False)
    temp.replace(target)
    return combined[AUDIT_COLUMNS]


def _iso(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def publish_manual_reports(
    reports: pd.DataFrame | None = None,
    *,
    audit_path: str | Path = AUDIT_FILE,
    output_path: str | Path = WEB_FILE,
) -> dict[str, object]:
    submissions = load_manual_submissions(audit_path)
    items: list[dict[str, object]] = []
    represented: set[tuple[str, str, str]] = set()

    for row in submissions.to_dict("records"):
        item = {**row, "origin": "submission"}
        items.append(item)
        represented.add((row["ticker"], row["report_period"], row["result_eps_ttm"]))

    canonical = normalise_reports(reports) if reports is not None else load_reports()
    canonical = canonical.loc[
        canonical["verified"]
        & ~canonical["source"].astype(str).str.startswith("Yahoo Finance")
        & canonical["eps_ttm"].notna()
    ]
    canonical = (
        canonical.sort_values(["ticker", "effective_date", "period_end"])
        .groupby("ticker", as_index=False, sort=False)
        .tail(1)
    )
    for row in canonical.to_dict("records"):
        eps_ttm = str(float(row["eps_ttm"]))
        key = (str(row["ticker"]), str(row["report_period"]), eps_ttm)
        if key in represented:
            continue
        currency_match = re.search(r"(?:^|;\s*)report_currency=([A-Za-z]{3})(?:;|$)", str(row["notes"]))
        items.append(
            {
                "submission_id": "",
                "ticker": str(row["ticker"]),
                "report_period": str(row["report_period"]),
                "period_end": _iso(row["period_end"])[:10],
                "published_at": _iso(row["published_at"]),
                "effective_date": _iso(row["effective_date"])[:10],
                "input_metric": "eps_ttm",
                "input_eps": eps_ttm,
                "result_eps_ttm": eps_ttm,
                "eps_currency": currency_match.group(1).upper() if currency_match else "",
                "source": str(row["source"]),
                "notes": "",
                "submitted_at": _iso(row["verified_at"]),
                "origin": "canonical",
            }
        )

    items.sort(
        key=lambda item: (
            str(item["published_at"] or item["effective_date"]),
            str(item["submitted_at"]),
        ),
        reverse=True,
    )
    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "submissions": items,
    }
    write_json_atomic(output_path, payload)
    return payload
