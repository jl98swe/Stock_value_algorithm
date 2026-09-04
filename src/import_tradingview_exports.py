from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import ROOT

MAPPING_FILE = ROOT / "config" / "ticker_mapping.csv"
STOCKS_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
REPORTS_FILE = ROOT / "data" / "fundamentals" / "reports.csv"
EXISTING_OVERRIDES_FILE = ROOT / "data" / "fundamentals" / "tradingview_eps_overrides.csv"
OUTPUT_FILE = EXISTING_OVERRIDES_FILE
AUDIT_FILE = ROOT / "data" / "derived" / "tradingview_eps_overrides_audit.csv"

SOURCE = "TradingView / EARNINGS_PER_SHARE_DILUTED TTM"
OUTPUT_COLUMNS = [
    "ticker",
    "report_period",
    "period_end",
    "report_date",
    "eps_ttm",
    "currency",
    "source",
    "report_date_status",
]


@dataclass(frozen=True)
class ExportFile:
    ticker: str
    tradingview_symbol: str
    path: Path


def _quarter_label(values: pd.Series) -> pd.Series:
    periods = values.dt.to_period("Q")
    return periods.astype(str).str.replace("Q", "-Q", regex=False)


def _symbol_from_filename(path: Path) -> str | None:
    name = path.stem
    patterns = (
        r"^OMXSTO_DLY_(.+), 3M$",
        r"^(.+)_3M$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, name)
        if match:
            return match.group(1)
    return None


def _discover_exports(input_dirs: list[Path], mapping: pd.DataFrame) -> list[ExportFile]:
    by_symbol = {
        str(row.tradingview_symbol).split(":", 1)[-1]: (
            str(row.borsdata_ticker),
            str(row.tradingview_symbol),
        )
        for row in mapping.itertuples(index=False)
    }
    discovered: dict[str, ExportFile] = {}
    for input_dir in input_dirs:
        for path in sorted(input_dir.rglob("*.csv")):
            symbol = _symbol_from_filename(path)
            if symbol not in by_symbol:
                continue
            ticker, tradingview_symbol = by_symbol[symbol]
            if ticker in discovered:
                raise ValueError(
                    f"Flera TradingView-exporter hittades för {ticker}: "
                    f"{discovered[ticker].path} och {path}"
                )
            discovered[ticker] = ExportFile(ticker, tradingview_symbol, path)

    missing = sorted(set(mapping["borsdata_ticker"].astype(str)) - set(discovered))
    if missing:
        raise ValueError(f"TradingView-export saknas för: {', '.join(missing)}")
    return [discovered[str(ticker)] for ticker in mapping["borsdata_ticker"]]


def _load_report_date_lookup(mapping: pd.DataFrame) -> dict[tuple[str, str], tuple[pd.Timestamp, str]]:
    """Returnera rapportdatum per ticker och kalenderkvartal för periodslutet."""

    yahoo_to_borsdata = dict(
        zip(mapping["yahoo_ticker"].astype(str), mapping["borsdata_ticker"].astype(str), strict=False)
    )
    candidates: list[pd.DataFrame] = []

    if REPORTS_FILE.exists():
        reports = pd.read_csv(REPORTS_FILE)
        reports["ticker"] = reports["ticker"].astype(str).map(yahoo_to_borsdata)
        reports["period_end"] = pd.to_datetime(reports["period_end"], errors="coerce")
        reports["report_date"] = pd.to_datetime(reports["effective_date"], errors="coerce")
        reports = reports.dropna(subset=["ticker", "period_end", "report_date"])
        reports["report_period"] = _quarter_label(reports["period_end"])
        reports["status"] = "canonical_period_bucket"
        candidates.append(reports[["ticker", "report_period", "report_date", "status"]])

    if EXISTING_OVERRIDES_FILE.exists():
        existing = pd.read_csv(EXISTING_OVERRIDES_FILE, encoding="utf-8-sig")
        existing["report_date"] = pd.to_datetime(existing.get("report_date"), errors="coerce")
        existing = existing.dropna(subset=["ticker", "report_period", "report_date"])
        existing["status"] = "existing_tradingview_override"
        candidates.insert(0, existing[["ticker", "report_period", "report_date", "status"]])

    if not candidates:
        return {}

    combined = pd.concat(candidates, ignore_index=True)
    combined["priority"] = combined["status"].eq("existing_tradingview_override").astype(int)
    combined = (
        combined.sort_values(["ticker", "report_period", "priority", "report_date"])
        .drop_duplicates(["ticker", "report_period"], keep="last")
    )
    return {
        (str(row.ticker), str(row.report_period)): (pd.Timestamp(row.report_date), str(row.status))
        for row in combined.itertuples(index=False)
    }


def _max_unchanged_run(values: pd.Series) -> int:
    if values.empty:
        return 0
    groups = values.ne(values.shift()).cumsum()
    return int(values.groupby(groups).size().max())


def build_overrides(
    input_dirs: list[Path],
    *,
    as_of_date: pd.Timestamp,
    first_period: str = "2018-Q3",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping = pd.read_csv(MAPPING_FILE, encoding="utf-8-sig")
    stocks = pd.read_csv(STOCKS_FILE, encoding="utf-8-sig")
    price_currency_by_yahoo = dict(
        zip(stocks["ticker"].astype(str), stocks["price_currency"].astype(str), strict=False)
    )
    currency_by_ticker = {
        str(row.borsdata_ticker): price_currency_by_yahoo.get(str(row.yahoo_ticker), "")
        for row in mapping.itertuples(index=False)
    }
    date_lookup = _load_report_date_lookup(mapping)
    exports = _discover_exports(input_dirs, mapping)
    current_period = as_of_date.to_period("Q")

    output_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for export in exports:
        raw = pd.read_csv(export.path, encoding="utf-8-sig")
        required = ["time", "Diluted EPS TTM"]
        missing_columns = [column for column in required if column not in raw.columns]
        if missing_columns:
            raise ValueError(f"{export.path.name} saknar kolumner: {', '.join(missing_columns)}")

        raw["time"] = pd.to_datetime(raw["time"], errors="coerce")
        raw["eps_ttm"] = pd.to_numeric(raw["Diluted EPS TTM"], errors="coerce")
        raw = raw.dropna(subset=["time", "eps_ttm"]).sort_values("time").reset_index(drop=True)
        raw["quarter"] = raw["time"].dt.to_period("Q")
        raw = raw.loc[raw["quarter"] >= pd.Period(first_period.replace("-", ""), freq="Q")].copy()

        current_action = "not_present"
        current = raw.index[raw["quarter"].eq(current_period)]
        if len(current):
            last_index = int(current[-1])
            unchanged = last_index > 0 and raw.loc[last_index, "eps_ttm"] == raw.loc[last_index - 1, "eps_ttm"]
            if unchanged:
                raw = raw.drop(index=last_index).reset_index(drop=True)
                current_action = "dropped_unchanged"
            else:
                current_action = "kept_changed"

        raw["report_period"] = _quarter_label(raw["time"])
        raw["period_end"] = raw["quarter"].dt.end_time.dt.normalize()
        missing_dates = 0
        statuses: list[str] = []
        for row in raw.itertuples(index=False):
            report_date, date_status = date_lookup.get(
                (export.ticker, str(row.report_period)),
                (pd.NaT, "missing"),
            )
            if (
                pd.isna(report_date)
                and row.quarter == current_period
                and current_action == "kept_changed"
            ):
                # The changed value is already visible in the live TradingView
                # export.  Use the export's as-of date as a conservative
                # effective date when the actual report date is unavailable.
                report_date = as_of_date.normalize()
                date_status = "observed_in_export"
            if pd.isna(report_date):
                missing_dates += 1
            statuses.append(date_status)
            output_rows.append(
                {
                    "ticker": export.ticker,
                    "report_period": str(row.report_period),
                    "period_end": pd.Timestamp(row.period_end),
                    "report_date": report_date,
                    "eps_ttm": round(float(row.eps_ttm), 4),
                    "currency": currency_by_ticker.get(export.ticker, ""),
                    "source": SOURCE,
                    "report_date_status": date_status,
                }
            )

        audit_rows.append(
            {
                "ticker": export.ticker,
                "tradingview_symbol": export.tradingview_symbol,
                "source_file": export.path.name,
                "raw_rows": len(pd.read_csv(export.path, encoding="utf-8-sig")),
                "eps_rows_from_2018_q3": len(raw) + (1 if current_action == "dropped_unchanged" else 0),
                "output_rows": len(raw),
                "first_period": raw["report_period"].iloc[0] if len(raw) else "",
                "last_period": raw["report_period"].iloc[-1] if len(raw) else "",
                "current_quarter_action": current_action,
                "missing_report_dates": missing_dates,
                "max_identical_eps_quarters": _max_unchanged_run(raw["eps_ttm"]),
                "warning": "long_unchanged_run" if _max_unchanged_run(raw["eps_ttm"]) >= 4 else "",
            }
        )

    overrides = pd.DataFrame(output_rows, columns=OUTPUT_COLUMNS)
    if overrides.duplicated(["ticker", "report_period"]).any():
        raise ValueError("Normaliserad TradingView-data innehåller dubbla ticker + report_period")
    if overrides[["ticker", "report_period", "period_end", "eps_ttm", "currency"]].isna().any().any():
        raise ValueError("Normaliserad TradingView-data saknar obligatoriska värden")
    return overrides.sort_values(["ticker", "period_end"]).reset_index(drop=True), pd.DataFrame(audit_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalisera TradingView 3M-exporter till EPS TTM-overrides.")
    parser.add_argument("--input-dir", action="append", required=True, type=Path)
    parser.add_argument("--as-of-date", required=True, type=pd.Timestamp)
    parser.add_argument("--first-period", default="2018-Q3")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    parser.add_argument("--audit-output", type=Path, default=AUDIT_FILE)
    args = parser.parse_args()

    overrides, audit = build_overrides(
        [path.resolve() for path in args.input_dir],
        as_of_date=args.as_of_date,
        first_period=args.first_period,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    output = overrides.copy()
    output["period_end"] = output["period_end"].dt.strftime("%Y-%m-%d")
    output["report_date"] = output["report_date"].dt.strftime("%Y-%m-%d").fillna("")
    output.to_csv(args.output, index=False, encoding="utf-8-sig")
    audit.to_csv(args.audit_output, index=False, encoding="utf-8-sig")
    print(
        f"Skrev {len(output)} TradingView-rader för {output['ticker'].nunique()} tickers. "
        f"Pågående oförändrad kvartalsrad togs bort för "
        f"{audit['current_quarter_action'].eq('dropped_unchanged').sum()} tickers."
    )


if __name__ == "__main__":
    main()
