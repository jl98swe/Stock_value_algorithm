"""Import paid point-in-time EPS history into the canonical report store.

The importer intentionally requires an effective trading date. It never maps a
period-end date to the market automatically, because that would introduce
look-ahead bias in backtests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .config import ROOT
from .fundamentals import REPORT_COLUMNS, load_reports, normalise_reports, save_reports
from .utils import write_json_atomic


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _load_mapping(path: str | Path) -> dict[str, Any]:
    target = _resolve(path)
    if not target.exists():
        raise FileNotFoundError(target)
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def _read_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError("Historikimport stöder CSV, XLSX/XLS och JSON")


def transform_input(frame: pd.DataFrame, mapping: dict[str, Any]) -> pd.DataFrame:
    columns = mapping.get("columns", {})
    defaults = mapping.get("defaults", {})
    output = pd.DataFrame(index=frame.index)
    for canonical in REPORT_COLUMNS:
        provider_column = columns.get(canonical, canonical)
        if provider_column in frame.columns:
            output[canonical] = frame[provider_column]
        else:
            output[canonical] = defaults.get(canonical, pd.NA)

    if "source" in defaults:
        output["source"] = output["source"].fillna(defaults["source"])
    if "verified" in defaults:
        output["verified"] = output["verified"].fillna(defaults["verified"])
    if "verified_at" in defaults:
        output["verified_at"] = output["verified_at"].fillna(defaults["verified_at"])
    output["verified_at"] = output["verified_at"].fillna(datetime.now(timezone.utc).isoformat())
    return normalise_reports(output)


def validate_import(frame: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if frame.empty:
        errors.append("Importfilen gav inga giltiga rader")
        return errors
    for column in ("ticker", "report_period", "published_at", "effective_date", "eps_ttm"):
        missing = int(frame[column].isna().sum())
        if missing:
            errors.append(f"{missing} rader saknar {column}")
    if (~frame["verified"]).any():
        errors.append("Alla historikrader måste vara verifierade innan de får användas")
    if frame.duplicated(["ticker", "effective_date"], keep=False).any():
        duplicates = frame.loc[frame.duplicated(["ticker", "effective_date"], keep=False), ["ticker", "effective_date"]]
        errors.append(f"Dubbla ticker/effective_date: {duplicates.to_dict(orient='records')[:5]}")
    if (frame["published_at"].dt.tz_convert(None).dt.normalize() > frame["effective_date"]).any():
        errors.append("Minst en effective_date ligger före publiceringsdatum")
    return errors


def import_history(
    input_path: str | Path,
    *,
    mapping_path: str | Path = "config/history_import_mapping.yml",
    replace_tickers: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    path = _resolve(input_path)
    mapping = _load_mapping(mapping_path)
    incoming = transform_input(_read_input(path), mapping)
    errors = validate_import(incoming)
    if errors:
        raise ValueError("; ".join(errors))

    existing = load_reports()
    tickers = sorted(incoming["ticker"].unique().tolist())
    if replace_tickers:
        existing = existing.loc[~existing["ticker"].isin(tickers)]
    else:
        keys = set(zip(incoming["ticker"].astype(str), incoming["report_period"].astype(str), strict=False))
        keep = [
            (str(row.ticker), str(row.report_period)) not in keys
            for row in existing.itertuples(index=False)
        ]
        existing = existing.loc[keep]

    combined = pd.concat([existing, incoming], ignore_index=True)
    combined = normalise_reports(combined)
    audit = {
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "input": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "mapping": str(_resolve(mapping_path).relative_to(ROOT)),
        "row_count": int(len(incoming)),
        "tickers": tickers,
        "minimum_effective_date": incoming["effective_date"].min().date().isoformat(),
        "maximum_effective_date": incoming["effective_date"].max().date().isoformat(),
        "replace_tickers": replace_tickers,
        "dry_run": dry_run,
    }
    if not dry_run:
        save_reports(combined)
        write_json_atomic(ROOT / "data/derived/history_import_audit.json", audit, pretty=True)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Importera köpt point-in-time EPS-historik")
    parser.add_argument("--input", required=True)
    parser.add_argument("--mapping", default="config/history_import_mapping.yml")
    parser.add_argument("--replace-tickers", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(import_history(args.input, mapping_path=args.mapping, replace_tickers=args.replace_tickers, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
