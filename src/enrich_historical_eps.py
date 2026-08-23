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
REPORT_DATE_CACHE_FILE = ROOT / "data" / "fundamentals" / "eps_report_date_cache.csv"
OUTPUT_METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
AUDIT_FILE = ROOT / "data" / "derived" / "eps_report_date_audit.csv"

SOURCE_COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
OUTPUT_COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
CACHE_COLUMNS = ["ticker", "report_period", "report_date"]
STOCKHOLM_TZ = "Europe/Stockholm"
MAX_LATEST_REPORT_AGE_DAYS = 240
MAX_REPORT_GAP_DAYS = 140


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


def _load_report_date_cache(path: Path = REPORT_DATE_CACHE_FILE) -> dict[tuple[str, str], pd.Timestamp]:
    if not path.exists() or path.stat().st_size == 0:
        return {}

    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in CACHE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Rapportdatum-cachen saknar kolumner: {', '.join(missing)}")

    frame = frame[CACHE_COLUMNS].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["report_period"] = frame["report_period"].astype(str).str.strip()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame = frame.dropna(subset=["ticker", "report_period", "report_date"])
    frame = frame.drop_duplicates(["ticker", "report_period"], keep="last")

    return {
        (str(row.ticker), str(row.report_period)): pd.Timestamp(row.report_date).normalize()
        for row in frame.itertuples(index=False)
    }


def _write_report_date_cache(
    cache: dict[tuple[str, str], pd.Timestamp],
    path: Path = REPORT_DATE_CACHE_FILE,
) -> None:
    rows = [
        {"ticker": ticker, "report_period": period, "report_date": pd.Timestamp(report_date).date().isoformat()}
        for (ticker, period), report_date in cache.items()
    ]
    frame = pd.DataFrame(rows, columns=CACHE_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(
            ["ticker", "report_period"],
            key=lambda column: column if column.name == "ticker" else column.map(_period_key),
        ).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _stockholm_calendar_date(value: object) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return pd.Timestamp(timestamp.tz_convert(STOCKHOLM_TZ).date())


def _latest_contiguous_quarterly_suffix(dates: list[pd.Timestamp]) -> list[pd.Timestamp]:
    ordered = sorted(set(dates))
    if not ordered:
        return []
    suffix = [ordered[-1]]
    for previous in reversed(ordered[:-1]):
        gap_days = (suffix[0] - previous).days
        if gap_days > MAX_REPORT_GAP_DAYS:
            break
        suffix.insert(0, previous)
    return suffix


def _past_earnings_dates(yahoo_ticker: str, wanted: int) -> list[pd.Timestamp]:
    limit = min(100, max(20, wanted + 8))
    dates = yf.Ticker(yahoo_ticker).get_earnings_dates(limit=limit, offset=1)
    if dates is None or dates.empty:
        return []

    now_utc = pd.Timestamp.now(tz="UTC")
    calendar_dates: list[pd.Timestamp] = []

    for index in dates.index:
        timestamp = pd.to_datetime(index, errors="coerce")
        if pd.isna(timestamp):
            continue
        timestamp = pd.Timestamp(timestamp)
        comparison = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        if comparison > now_utc:
            continue
        local_date = _stockholm_calendar_date(timestamp)
        if local_date is not None:
            calendar_dates.append(local_date)

    result = sorted(set(calendar_dates))
    if not result:
        return []

    today_stockholm = pd.Timestamp.now(tz=STOCKHOLM_TZ).tz_localize(None).normalize()
    latest_age = (today_stockholm - result[-1]).days
    if latest_age > MAX_LATEST_REPORT_AGE_DAYS:
        raise ValueError(
            f"Yahoo-historiken är för gammal: senaste datum {result[-1].date().isoformat()} "
            f"({latest_age} dagar sedan)"
        )

    # Yahoo kan ha luckor på flera kvartal eller år. Om vi bara tog de senaste
    # N datumen skulle alla äldre perioder då förskjutas. Använd därför bara
    # den senaste sammanhängande kvartalssekvensen och lämna äldre luckor tomma.
    return _latest_contiguous_quarterly_suffix(result)


def _align_dates(periods: list[str], dates: list[pd.Timestamp]) -> dict[str, pd.Timestamp]:
    ordered_periods = sorted(periods, key=_period_key)
    if not dates:
        return {}
    count = min(len(ordered_periods), len(dates))
    selected_periods = ordered_periods[-count:]
    selected_dates = sorted(dates)[-count:]
    return dict(zip(selected_periods, selected_dates, strict=True))


def _sibling_share_class_proxy(yahoo_ticker: str, available: set[str]) -> str | None:
    for own, other in (("-B.ST", "-A.ST"), ("-A.ST", "-B.ST")):
        if yahoo_ticker.endswith(own):
            candidate = yahoo_ticker[: -len(own)] + other
            if candidate in available:
                return candidate
    return None


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
    report_date_cache_file: Path = REPORT_DATE_CACHE_FILE,
    metadata_file: Path = METADATA_FILE,
    output_metadata_file: Path = OUTPUT_METADATA_FILE,
    audit_file: Path = AUDIT_FILE,
) -> pd.DataFrame:
    source = _load_source(source_file)
    mapping = _load_mapping(mapping_file)
    lookup = mapping.set_index("borsdata_ticker")["yahoo_ticker"]
    report_date_cache = _load_report_date_cache(report_date_cache_file)

    source["source_ticker"] = source["ticker"]
    source["ticker"] = source["source_ticker"].map(lookup)
    if source["ticker"].isna().any():
        unknown = sorted(source.loc[source["ticker"].isna(), "source_ticker"].unique().tolist())
        raise ValueError(f"Saknar Yahoo-mappning för: {', '.join(unknown)}")

    available_yahoo = set(source["ticker"].astype(str))
    output_parts: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []

    for source_ticker, group in source.groupby("source_ticker", sort=True):
        yahoo_ticker = str(group["ticker"].iloc[0])
        periods = group["report_period"].astype(str).tolist()
        source_dates = group.set_index("report_period")["report_date"].to_dict()
        date_source_ticker = yahoo_ticker

        try:
            yahoo_dates = _past_earnings_dates(yahoo_ticker, len(periods))
            error = ""
        except Exception as exc:
            yahoo_dates = []
            error = str(exc)
            print(f"VARNING {yahoo_ticker}: kunde inte använda Yahoo-rapportdatum: {exc}")

        if not yahoo_dates:
            proxy = _sibling_share_class_proxy(yahoo_ticker, available_yahoo)
            if proxy is not None:
                try:
                    yahoo_dates = _past_earnings_dates(proxy, len(periods))
                    if yahoo_dates:
                        date_source_ticker = proxy
                        error = f"Rapportdatum hämtade via systeraktien {proxy}"
                except Exception as exc:
                    if error:
                        error += f"; proxy {proxy}: {exc}"
                    else:
                        error = f"proxy {proxy}: {exc}"

        aligned = _align_dates(periods, yahoo_dates)
        enriched = group.copy()
        filled = 0
        reused = 0

        for idx, row in enriched.iterrows():
            period = str(row["report_period"])
            cache_key = (yahoo_ticker, period)
            explicit = source_dates.get(period)
            cached = report_date_cache.get(cache_key)

            # Prioritet: explicit datum i källfilen > redan etablerat datum i cache
            # > ny Yahoo-mappning. Därmed kan en nytillkommen Yahoo-rapport aldrig
            # flytta äldre ticker + report_period ett kvartal framåt.
            if pd.notna(explicit):
                chosen = pd.Timestamp(explicit).normalize()
                enriched.at[idx, "report_date"] = chosen
                report_date_cache[cache_key] = chosen
            elif cached is not None:
                enriched.at[idx, "report_date"] = cached
                reused += 1
            elif period in aligned:
                chosen = pd.Timestamp(aligned[period]).normalize()
                enriched.at[idx, "report_date"] = chosen
                report_date_cache[cache_key] = chosen
                filled += 1

        mapped_count = int(enriched["report_date"].notna().sum())
        status = "complete" if mapped_count == len(enriched) else ("partial" if mapped_count else "missing")
        audit_rows.append(
            {
                "source_ticker": source_ticker,
                "yahoo_ticker": yahoo_ticker,
                "date_source_ticker": date_source_ticker,
                "periods": len(enriched),
                "yahoo_dates_found": len(yahoo_dates),
                "dates_mapped": mapped_count,
                "cached_dates_reused": reused,
                "new_dates_filled": filled,
                "status": status,
                "latest_yahoo_date": yahoo_dates[-1].date().isoformat() if yahoo_dates else "",
                "error": error,
            }
        )
        print(
            f"{source_ticker} -> {yahoo_ticker}: {mapped_count}/{len(enriched)} "
            f"rapportdatum ({status}, {reused} från cache, {filled} nya, källa {date_source_ticker})"
        )
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
    _write_report_date_cache(report_date_cache, report_date_cache_file)

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
    parser.add_argument("--report-date-cache", type=Path, default=REPORT_DATE_CACHE_FILE)
    args = parser.parse_args()
    enrich(
        source_file=args.source,
        mapping_file=args.mapping,
        output_file=args.output,
        report_date_cache_file=args.report_date_cache,
    )


if __name__ == "__main__":
    main()
