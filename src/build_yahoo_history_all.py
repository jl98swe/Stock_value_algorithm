from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yfinance as yf

from .align_historical_eps_to_yahoo import _load_yahoo
from .config import ROOT
from .earnings import latest_earnings
from .fundamentals import load_reports

TIMESERIES_FILE = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
OUTPUT_FILE = ROOT / "data" / "fundamentals" / "yahoo_history_all.csv"
AUDIT_FILE = ROOT / "data" / "derived" / "yahoo_history_all_audit.csv"
METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
STOCKHOLM_TZ = "Europe/Stockholm"
MAX_REPORT_LAG_DAYS = 140


def _stockholm_date(value: object) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return pd.Timestamp(timestamp.tz_convert(STOCKHOLM_TZ).date())


def _fetch_earnings_dates(ticker: str) -> list[pd.Timestamp]:
    try:
        frame = yf.Ticker(ticker).get_earnings_dates(limit=100, offset=1)
    except Exception as exc:
        print(f"VARNING {ticker}: historiska rapportdatum kunde inte hämtas: {exc}")
        return []
    if frame is None or frame.empty:
        return []

    now_utc = pd.Timestamp.now(tz="UTC")
    dates: list[pd.Timestamp] = []
    for index in frame.index:
        timestamp = pd.to_datetime(index, errors="coerce")
        if pd.isna(timestamp):
            continue
        timestamp = pd.Timestamp(timestamp)
        comparison = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        if comparison > now_utc:
            continue
        local_date = _stockholm_date(timestamp)
        if local_date is not None:
            dates.append(local_date)
    return sorted(set(dates))


def _fetch_price_currency(ticker: str) -> str:
    symbol = yf.Ticker(ticker)
    try:
        fast = symbol.fast_info
        currency = str(fast.get("currency") or "").strip().upper()
        if currency:
            return currency
    except Exception:
        pass
    try:
        currency = str((symbol.get_info() or {}).get("currency") or "").strip().upper()
        if currency:
            return currency
    except Exception as exc:
        print(f"VARNING {ticker}: handelsvaluta kunde inte hämtas: {exc}")
    return ""


def _existing_period_dates() -> dict[tuple[str, pd.Timestamp], pd.Timestamp]:
    reports = load_reports()
    if reports.empty:
        return {}
    rows = reports.dropna(subset=["ticker", "period_end", "effective_date"]).copy()
    result: dict[tuple[str, pd.Timestamp], pd.Timestamp] = {}
    for row in rows.itertuples(index=False):
        key = (str(row.ticker), pd.Timestamp(row.period_end).normalize())
        result[key] = pd.Timestamp(row.effective_date).normalize()
    return result


def _current_snapshot_dates() -> dict[tuple[str, pd.Timestamp], pd.Timestamp]:
    current = latest_earnings()
    if current.empty:
        return {}
    current = current.dropna(subset=["ticker", "period_end", "report_date"])
    result: dict[tuple[str, pd.Timestamp], pd.Timestamp] = {}
    for row in current.itertuples(index=False):
        result[(str(row.ticker), pd.Timestamp(row.period_end).normalize())] = pd.Timestamp(row.report_date).normalize()
    return result


def _map_report_dates(
    ticker: str,
    periods: pd.DataFrame,
    yahoo_dates: list[pd.Timestamp],
    existing_dates: dict[tuple[str, pd.Timestamp], pd.Timestamp],
    snapshot_dates: dict[tuple[str, pd.Timestamp], pd.Timestamp],
) -> pd.DataFrame:
    result = periods.sort_values("as_of_date").copy()
    result["report_date"] = pd.NaT
    result["date_status"] = "missing"

    used: set[pd.Timestamp] = set()
    previous_report: pd.Timestamp | None = None
    for idx, row in result.iterrows():
        period_end = pd.Timestamp(row["as_of_date"]).normalize()
        key = (ticker, period_end)

        chosen = existing_dates.get(key)
        status = "existing_canonical"
        if chosen is None:
            candidate = snapshot_dates.get(key)
            if candidate is not None:
                lag = int((candidate - period_end).days)
                if 0 <= lag <= MAX_REPORT_LAG_DAYS:
                    chosen = candidate
                    status = "current_snapshot"

        if chosen is None:
            candidates = [
                date
                for date in yahoo_dates
                if date not in used
                and date >= period_end
                and int((date - period_end).days) <= MAX_REPORT_LAG_DAYS
                and (previous_report is None or date > previous_report)
            ]
            if candidates:
                chosen = min(candidates)
                status = "yahoo_earnings_date"

        if chosen is not None:
            chosen = pd.Timestamp(chosen).normalize()
            result.at[idx, "report_date"] = chosen
            result.at[idx, "date_status"] = status
            used.add(chosen)
            previous_report = chosen

    return result


def _load_metadata() -> pd.DataFrame:
    if not METADATA_FILE.exists() or METADATA_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=["ticker", "company", "isin", "price_currency", "report_currency"])
    frame = pd.read_csv(METADATA_FILE, encoding="utf-8-sig")
    for column in ["ticker", "company", "isin", "price_currency", "report_currency"]:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[["ticker", "company", "isin", "price_currency", "report_currency"]].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    for column in ["price_currency", "report_currency"]:
        frame[column] = frame[column].fillna("").astype(str).str.strip().str.upper()
    return frame.drop_duplicates("ticker", keep="last")


def _extend_metadata(history: pd.DataFrame, *, workers: int) -> pd.DataFrame:
    existing = _load_metadata()
    existing_map = existing.set_index("ticker") if not existing.empty else pd.DataFrame()
    tickers = sorted(history["ticker"].astype(str).unique())

    missing_price = [
        ticker
        for ticker in tickers
        if existing_map.empty
        or ticker not in existing_map.index
        or not str(existing_map.loc[ticker, "price_currency"]).strip()
    ]
    fetched_price: dict[str, str] = {}
    if missing_price:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(missing_price)))) as executor:
            futures = {executor.submit(_fetch_price_currency, ticker): ticker for ticker in missing_price}
            for index, future in enumerate(as_completed(futures), start=1):
                ticker = futures[future]
                try:
                    fetched_price[ticker] = str(future.result() or "").upper()
                except Exception as exc:
                    print(f"VARNING {ticker}: handelsvalutahämtning misslyckades: {exc}")
                    fetched_price[ticker] = ""
                print(f"Handelsvaluta {index}/{len(missing_price)} klar: {ticker}")

    rows: list[dict[str, str]] = []
    for ticker in tickers:
        subset = history.loc[history["ticker"] == ticker].sort_values("as_of_date")
        currencies = [value for value in subset["currency_code"].astype(str).str.upper().unique() if value]
        report_currency = currencies[-1] if currencies else ""

        company = ""
        isin = ""
        price_currency = fetched_price.get(ticker, "")
        if not existing_map.empty and ticker in existing_map.index:
            old = existing_map.loc[ticker]
            company = str(old.get("company", "") or "")
            isin = str(old.get("isin", "") or "")
            price_currency = str(old.get("price_currency", "") or price_currency).strip().upper()
            old_report = str(old.get("report_currency", "") or "").strip().upper()
            if old_report:
                report_currency = old_report

        rows.append(
            {
                "ticker": ticker,
                "company": company,
                "isin": isin,
                "price_currency": price_currency,
                "report_currency": report_currency,
            }
        )

    output = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(METADATA_FILE, index=False)
    return output


def build(
    timeseries_file: Path = TIMESERIES_FILE,
    output_file: Path = OUTPUT_FILE,
    audit_file: Path = AUDIT_FILE,
    *,
    workers: int = 4,
) -> pd.DataFrame:
    raw = pd.read_csv(timeseries_file)
    yahoo = _load_yahoo(timeseries_file)
    if yahoo.empty:
        raise ValueError("Yahoo-timeseries innehåller ingen trailingDilutedEPS-historik.")

    existing_dates = _existing_period_dates()
    snapshot_dates = _current_snapshot_dates()
    tickers = sorted(yahoo["ticker"].astype(str).unique())

    date_map: dict[str, list[pd.Timestamp]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {executor.submit(_fetch_earnings_dates, ticker): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                date_map[ticker] = future.result()
            except Exception as exc:
                print(f"VARNING {ticker}: rapportdatumshämtning misslyckades: {exc}")
                date_map[ticker] = []
            print(f"Historiska rapportdatum {index}/{len(tickers)} klar: {ticker}")

    parts: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []
    for ticker, group in yahoo.groupby("ticker", sort=True):
        mapped = _map_report_dates(
            str(ticker),
            group,
            date_map.get(str(ticker), []),
            existing_dates,
            snapshot_dates,
        )
        mapped = mapped.rename(
            columns={
                "as_of_date": "period_end",
                "value": "eps_ttm",
                "currency_code": "currency",
            }
        )
        mapped["ticker"] = str(ticker)
        mapped = mapped[
            [
                "ticker",
                "period_end",
                "report_date",
                "eps_ttm",
                "currency",
                "alignment_status",
                "eps_source",
                "date_status",
            ]
        ]
        parts.append(mapped)

        audit_rows.append(
            {
                "ticker": str(ticker),
                "periods": len(mapped),
                "direct_periods": int((mapped["alignment_status"] == "yahoo_trailing_diluted").sum()),
                "reconstructed_periods": int((mapped["alignment_status"] == "yahoo_reconstructed_diluted_ttm").sum()),
                "report_dates_mapped": int(mapped["report_date"].notna().sum()),
                "report_dates_missing": int(mapped["report_date"].isna().sum()),
                "first_period_end": pd.to_datetime(mapped["period_end"]).min().date().isoformat(),
                "last_period_end": pd.to_datetime(mapped["period_end"]).max().date().isoformat(),
            }
        )

    output = pd.concat(parts, ignore_index=True).sort_values(["ticker", "period_end"]).reset_index(drop=True)
    output["period_end"] = pd.to_datetime(output["period_end"]).dt.strftime("%Y-%m-%d")
    output["report_date"] = pd.to_datetime(output["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_file, index=False)

    metadata = _extend_metadata(output.assign(as_of_date=pd.to_datetime(output["period_end"]), currency_code=output["currency"]), workers=workers)
    audit = pd.DataFrame(audit_rows).merge(
        metadata[["ticker", "price_currency", "report_currency"]], on="ticker", how="left"
    )
    audit["currency_ready"] = (
        audit["price_currency"].fillna("").astype(str).str.len().gt(0)
        & audit["report_currency"].fillna("").astype(str).str.len().gt(0)
    )
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_file, index=False)

    raw_tickers = raw["ticker"].nunique() if "ticker" in raw.columns else 0
    print(
        f"Yahoo direkt-historik klar: {len(output)} TTM-perioder för {output['ticker'].nunique()}/{raw_tickers} tickers; "
        f"{output['report_date'].notna().sum()} perioder har rapportdatum."
    )
    return output


if __name__ == "__main__":
    build()
