from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import ROOT

SOURCE_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history.csv"
MAPPING_FILE = ROOT / "config" / "ticker_mapping.csv"
METADATA_FILE = ROOT / "data" / "metadata" / "stocks.csv"
OUTPUT_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
OUTPUT_METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
AUDIT_FILE = ROOT / "data" / "derived" / "eps_report_date_audit.csv"

SOURCE_COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
OUTPUT_COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, encoding="utf-8-sig")


def _period_key(value: str) -> tuple[int, int]:
    text = str(value).strip().upper()
    try:
        year_text, quarter_text = text.split("-Q", 1)
        return int(year_text), int(quarter_text)
    except Exception as exc:
        raise ValueError(f"Ogiltig report_period: {value}") from exc


def _load_mapping(path: Path = MAPPING_FILE) -> pd.DataFrame:
    mapping = _read_csv(path)
    columns = ["borsdata_ticker", "tradingview_symbol", "yahoo_ticker"]
    missing = [column for column in columns if column not in mapping.columns]
    if missing:
        raise ValueError(f"Ticker-mappningen saknar kolumner: {', '.join(missing)}")
    mapping = mapping[columns].copy()
    for column in columns:
        mapping[column] = mapping[column].astype(str).str.strip()
    if mapping["borsdata_ticker"].duplicated().any():
        raise ValueError("Ticker-mappningen innehåller dubbla borsdata_ticker")
    if mapping["yahoo_ticker"].duplicated().any():
        duplicates = mapping.loc[mapping["yahoo_ticker"].duplicated(False), "yahoo_ticker"].tolist()
        raise ValueError(f"Ticker-mappningen innehåller dubbla Yahoo-tickers: {duplicates[:10]}")
    return mapping


def _load_source(path: Path = SOURCE_FILE) -> pd.DataFrame:
    frame = _read_csv(path)
    missing = [column for column in SOURCE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"EPS-historiken saknar kolumner: {', '.join(missing)}")
    frame = frame[SOURCE_COLUMNS].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["report_period"] = frame["report_period"].astype(str).str.strip()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame["eps_ttm"] = pd.to_numeric(frame["eps_ttm"], errors="coerce")
    frame["currency"] = frame["currency"].astype(str).str.strip().str.upper()
    if frame[["ticker", "report_period", "eps_ttm", "currency"]].isna().any().any():
        raise ValueError("EPS-historiken innehåller saknad ticker, period, EPS eller valuta")
    if frame.duplicated(["ticker", "report_period"]).any():
        raise ValueError("EPS-historiken innehåller dubbla ticker + report_period")
    for period in frame["report_period"]:
        _period_key(period)
    return frame


def _past_earnings_dates(yahoo_ticker: str, wanted: int) -> list[pd.Timestamp]:
    limit = max(20, wanted + 8)
    dates = yf.Ticker(yahoo_ticker).get_earnings_dates(limit=limit, offset=1)
    if dates is None or dates.empty:
        return []

    now = pd.Timestamp.now(tz="UTC")
    preferred: list[pd.Timestamp] = []
    fallback: list[pd.Timestamp] = []
    has_reported_eps = "Reported EPS" in dates.columns

    for index, row in dates.iterrows():
        timestamp = pd.to_datetime(index, errors="coerce")
        if pd.isna(timestamp):
            continue
        timestamp = pd.Timestamp(timestamp)
        comparison = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        if comparison > now:
            continue
        calendar_date = pd.Timestamp(timestamp.date())
        fallback.append(calendar_date)
        if not has_reported_eps or pd.notna(row.get("Reported EPS")):
            preferred.append(calendar_date)

    chosen = preferred if preferred else fallback
    return sorted(set(chosen))


def _align_dates(periods: list[str], dates: list[pd.Timestamp]) -> dict[str, pd.Timestamp]:
    ordered_periods = sorted(periods, key=_period_key)
    if not dates:
        return {}
    count = min(len(ordered_periods), len(dates))
    # Align from the newest end. If Yahoo has incomplete older history, the
    # newest EPS periods still get the newest public report dates.
    selected_periods = ordered_periods[-count:]
    selected_dates = sorted(dates)[-count:]
    return dict(zip(selected_periods, selected_dates, strict=True))


def _canonical_metadata(mapping: pd.DataFrame, path: Path = METADATA_FILE) -> pd.DataFrame:
    metadata = _read_csv(path)
    required = ["ticker", "company", "isin", "price_currency", "report_currency"]
    missing = [column for column in required if column not in metadata.columns]
    if missing:
        raise ValueError(f"stocks.csv saknar kolumner: {', '.join(missing)}")
    metadata = metadata[required].copy()
    metadata["ticker"] = metadata["ticker"].astype(str).str.strip()
    lookup = mapping.set_index("borsdata_ticker")["yahoo_ticker"]
    metadata["source_ticker"] = metadata["ticker"]
    metadata["ticker"] = metadata["source_ticker"].map(lookup)
    if metadata["ticker"].isna().any():
        unknown = metadata.loc[metadata["ticker"].isna(), "source_ticker"].tolist()
        raise ValueError(f"Saknar Yahoo-mappning för metadata: {unknown[:20]}")
    return metadata[["ticker", "company", "isin", "price_currency", "report_currency"]].sort_values("ticker")


def enrich(
    source_file: Path = SOURCE_FILE,
    mapping_file: Path = MAPPING_FILE,
    output_file: Path = OUTPUT_FILE,
    metadata_file: Path = METADATA_FILE,
    output_metadata_file: Path = OUTPUT_METADATA_FILE,
    audit_file: Path = AUDIT_FILE,
) -> pd.DataFrame:
    source = _load_source(source_file)
    mapping = _load_mapping(mapping_file)
    lookup = mapping.set_index("borsdata_ticker")["yahoo_ticker"]

    source["source_ticker"] = source["ticker"]
    source["ticker"] = source["source_ticker"].map(lookup)
    if source["ticker"].isna().any():
        unknown = sorted(source.loc[source["ticker"].isna(), "source_ticker"].unique().tolist())
        raise ValueError(f"Saknar Yahoo-mappning för: {', '.join(unknown)}")

    output_parts: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []

    for source_ticker, group in source.groupby("source_ticker", sort=True):
        yahoo_ticker = str(group["ticker"].iloc[0])
        periods = group["report_period"].astype(str).tolist()
        existing_dates = group.set_index("report_period")["report_date"].to_dict()

        try:
            yahoo_dates = _past_earnings_dates(yahoo_ticker, len(periods))
            error = ""
        except Exception as exc:
            yahoo_dates = []
            error = str(exc)
            print(f"VARNING {yahoo_ticker}: kunde inte hämta historiska rapportdatum: {exc}")

        aligned = _align_dates(periods, yahoo_dates)
        enriched = group.copy()
        filled = 0
        for idx, row in enriched.iterrows():
            period = str(row["report_period"])
            existing = existing_dates.get(period)
            if pd.notna(existing):
                enriched.at[idx, "report_date"] = existing
            elif period in aligned:
                enriched.at[idx, "report_date"] = aligned[period]
                filled += 1

        mapped_count = int(enriched["report_date"].notna().sum())
        status = "complete" if mapped_count == len(enriched) else ("partial" if mapped_count else "missing")
        audit_rows.append(
            {
                "source_ticker": source_ticker,
                "yahoo_ticker": yahoo_ticker,
                "periods": len(enriched),
                "yahoo_dates_found": len(yahoo_dates),
                "dates_mapped": mapped_count,
                "new_dates_filled": filled,
                "status": status,
                "latest_yahoo_date": yahoo_dates[-1].date().isoformat() if yahoo_dates else "",
                "error": error,
            }
        )
        print(f"{source_ticker} -> {yahoo_ticker}: {mapped_count}/{len(enriched)} rapportdatum ({status})")
        output_parts.append(enriched)

    output = pd.concat(output_parts, ignore_index=True)
    output = output.sort_values(
        ["ticker", "report_period"],
        key=lambda column: column if column.name == "ticker" else column.map(_period_key),
    )
    output["report_date"] = pd.to_datetime(output["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    output = output[OUTPUT_COLUMNS]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_file, index=False)

    canonical_metadata = _canonical_metadata(mapping, metadata_file)
    output_metadata_file.parent.mkdir(parents=True, exist_ok=True)
    canonical_metadata.to_csv(output_metadata_file, index=False)

    audit = pd.DataFrame(audit_rows).sort_values("yahoo_ticker")
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_file, index=False)

    missing_rows = int(output["report_date"].isna().sum())
    print(
        f"Klar: {len(output)} EPS-rader, {output['ticker'].nunique()} bolag, "
        f"{missing_rows} rader utan rapportdatum."
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mappa historisk EPS TTM till Yahoo-tickers och komplettera publika rapportdatum."
    )
    parser.add_argument("--source", type=Path, default=SOURCE_FILE)
    parser.add_argument("--mapping", type=Path, default=MAPPING_FILE)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    enrich(source_file=args.source, mapping_file=args.mapping, output_file=args.output)


if __name__ == "__main__":
    main()
