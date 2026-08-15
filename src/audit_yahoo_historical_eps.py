from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from .config import ROOT
from .earnings import latest_earnings
from .fx import load_fx_history, load_stock_currencies

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
OUTPUT_FILE = ROOT / "data" / "derived" / "yahoo_reported_eps_ttm_audit.csv"
MAX_DATE_DELTA_DAYS = 7
LATEST_MATCH_TOLERANCE_PCT = 7.5


def _relative_error_pct(actual: float, expected: float) -> float:
    denominator = max(abs(float(expected)), 1e-9)
    return abs(float(actual) - float(expected)) / denominator * 100.0


def _fx_rate_before(
    date_value: pd.Timestamp,
    base_currency: str,
    quote_currency: str,
    fx: pd.DataFrame,
) -> float | None:
    base = str(base_currency).strip().upper()
    quote = str(quote_currency).strip().upper()
    if base == quote:
        return 1.0
    target = pd.Timestamp(date_value).tz_localize(None).normalize()
    pair = fx.loc[
        (fx["base_currency"] == base)
        & (fx["quote_currency"] == quote)
        & (fx["date"] < target),
        ["date", "rate"],
    ].sort_values("date")
    if pair.empty:
        return None
    value = pd.to_numeric(pd.Series([pair.iloc[-1]["rate"]]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def _normalise_event_date(value: object) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    timestamp = pd.Timestamp(timestamp)
    return pd.Timestamp(timestamp.date())


def _fetch_reported_eps_one(ticker: str) -> pd.DataFrame:
    try:
        dates = yf.Ticker(ticker).get_earnings_dates(limit=40)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo Reported EPS kunde inte hämtas: {exc}")
        return pd.DataFrame(columns=["ticker", "yahoo_event_date", "reported_eps", "yahoo_ttm_4q"])
    if dates is None or dates.empty or "Reported EPS" not in dates.columns:
        print(f"INFO {ticker}: Yahoo saknar historisk Reported EPS.")
        return pd.DataFrame(columns=["ticker", "yahoo_event_date", "reported_eps", "yahoo_ttm_4q"])

    rows: list[dict[str, object]] = []
    today = pd.Timestamp(datetime.now(ZoneInfo("Europe/Stockholm")).date())
    for index, row in dates.iterrows():
        event_date = _normalise_event_date(index)
        reported = pd.to_numeric(pd.Series([row.get("Reported EPS")]), errors="coerce").iloc[0]
        if event_date is None or event_date > today or pd.isna(reported):
            continue
        rows.append(
            {
                "ticker": ticker,
                "yahoo_event_date": event_date,
                "reported_eps": float(reported),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["ticker", "yahoo_event_date", "reported_eps", "yahoo_ttm_4q"])

    result = pd.DataFrame(rows)
    result = (
        result.sort_values("yahoo_event_date")
        .drop_duplicates("yahoo_event_date", keep="last")
        .reset_index(drop=True)
    )
    result["yahoo_ttm_4q"] = result["reported_eps"].rolling(4, min_periods=4).sum()
    return result


def _nearest_event(events: pd.DataFrame, report_date: pd.Timestamp) -> pd.Series | None:
    if events.empty:
        return None
    target = pd.Timestamp(report_date).normalize()
    candidates = events.copy()
    candidates["date_delta_days"] = (candidates["yahoo_event_date"] - target).dt.days.abs()
    candidates = candidates.sort_values(["date_delta_days", "yahoo_event_date"])
    best = candidates.iloc[0]
    if int(best["date_delta_days"]) > MAX_DATE_DELTA_DAYS:
        return None
    return best


def audit(
    history_file: Path = HISTORY_FILE,
    output_file: Path = OUTPUT_FILE,
    *,
    workers: int = 4,
) -> pd.DataFrame:
    history = pd.read_csv(history_file, encoding="utf-8-sig")
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    history["eps_ttm"] = pd.to_numeric(history["eps_ttm"], errors="coerce")
    history = history.dropna(subset=["ticker", "report_date", "eps_ttm"]).copy()
    history["ticker"] = history["ticker"].astype(str).str.strip()

    tickers = sorted(history["ticker"].unique().tolist())
    event_frames: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {executor.submit(_fetch_reported_eps_one, ticker): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                event_frames[ticker] = future.result()
            except Exception as exc:
                print(f"VARNING {ticker}: historisk Yahoo EPS misslyckades: {exc}")
                event_frames[ticker] = pd.DataFrame()
            print(f"Historisk Yahoo EPS {index}/{len(tickers)} klar: {ticker}")

    metadata = load_stock_currencies().set_index("ticker")
    fx = load_fx_history()
    current = latest_earnings()
    current_map = current.set_index("ticker") if not current.empty else pd.DataFrame()

    currency_basis: dict[str, str] = {}
    validation_error: dict[str, float] = {}
    for ticker in tickers:
        events = event_frames.get(ticker, pd.DataFrame())
        ticker_history = history.loc[history["ticker"] == ticker].sort_values("report_date")
        latest_history = ticker_history.iloc[-1]
        nearest = _nearest_event(events, pd.Timestamp(latest_history["report_date"]))
        if nearest is None or pd.isna(nearest.get("yahoo_ttm_4q")) or ticker not in metadata.index or current.empty or ticker not in current_map.index:
            currency_basis[ticker] = "unknown"
            validation_error[ticker] = np.nan
            continue

        report_currency = str(metadata.loc[ticker, "report_currency"]).strip().upper()
        price_currency = str(metadata.loc[ticker, "price_currency"]).strip().upper()
        reconstructed = float(nearest["yahoo_ttm_4q"])
        direct = float(current_map.loc[ticker, "eps_ttm"])
        observed_date = pd.Timestamp(current_map.loc[ticker, "observed_date"])

        raw_error = _relative_error_pct(reconstructed, direct)
        converted_error = np.nan
        rate = _fx_rate_before(observed_date, report_currency, price_currency, fx)
        if rate is not None:
            converted_error = _relative_error_pct(reconstructed * rate, direct)

        if report_currency == price_currency or raw_error <= converted_error or pd.isna(converted_error):
            basis = "price_currency" if report_currency != price_currency else "report_currency"
            best_error = raw_error
        else:
            basis = "report_currency"
            best_error = float(converted_error)
        currency_basis[ticker] = basis
        validation_error[ticker] = best_error

    rows: list[dict[str, object]] = []
    for item in history.sort_values(["ticker", "report_date", "report_period"]).itertuples(index=False):
        ticker = str(item.ticker)
        events = event_frames.get(ticker, pd.DataFrame())
        nearest = _nearest_event(events, pd.Timestamp(item.report_date))
        report_currency = str(metadata.loc[ticker, "report_currency"]).strip().upper() if ticker in metadata.index else str(item.currency).strip().upper()
        price_currency = str(metadata.loc[ticker, "price_currency"]).strip().upper() if ticker in metadata.index else report_currency
        basis = currency_basis.get(ticker, "unknown")
        ticker_validation_error = validation_error.get(ticker, np.nan)

        yahoo_event_date = pd.NaT
        reported_eps = np.nan
        yahoo_ttm_raw = np.nan
        date_delta_days = np.nan
        yahoo_ttm_report_currency = np.nan
        fx_rate = 1.0 if report_currency == price_currency else np.nan
        status = "missing_yahoo_history"

        if nearest is not None:
            yahoo_event_date = nearest["yahoo_event_date"]
            reported_eps = nearest["reported_eps"]
            yahoo_ttm_raw = nearest["yahoo_ttm_4q"]
            date_delta_days = nearest["date_delta_days"]
            if pd.notna(yahoo_ttm_raw):
                if report_currency == price_currency or basis == "report_currency":
                    yahoo_ttm_report_currency = float(yahoo_ttm_raw)
                    fx_rate = 1.0 if report_currency == price_currency else _fx_rate_before(pd.Timestamp(item.report_date), report_currency, price_currency, fx)
                elif basis == "price_currency":
                    fx_rate = _fx_rate_before(pd.Timestamp(item.report_date), report_currency, price_currency, fx)
                    if fx_rate is not None and fx_rate > 0:
                        yahoo_ttm_report_currency = float(yahoo_ttm_raw) / float(fx_rate)
                if pd.notna(yahoo_ttm_report_currency):
                    status = "usable" if pd.notna(ticker_validation_error) and ticker_validation_error <= LATEST_MATCH_TOLERANCE_PCT else "unvalidated_latest"
                else:
                    status = "missing_fx"
            else:
                status = "insufficient_4q_history"

        historical_error = (
            _relative_error_pct(float(yahoo_ttm_report_currency), float(item.eps_ttm))
            if pd.notna(yahoo_ttm_report_currency)
            else np.nan
        )
        rows.append(
            {
                "ticker": ticker,
                "report_period": item.report_period,
                "historical_report_date": pd.Timestamp(item.report_date).date().isoformat(),
                "historical_eps_ttm": float(item.eps_ttm),
                "report_currency": report_currency,
                "price_currency": price_currency,
                "yahoo_event_date": pd.Timestamp(yahoo_event_date).date().isoformat() if pd.notna(yahoo_event_date) else "",
                "date_delta_days": date_delta_days,
                "reported_quarter_eps": reported_eps,
                "yahoo_ttm_4q_raw": yahoo_ttm_raw,
                "yahoo_quarterly_currency_basis": basis,
                "fx_rate_report_to_price": fx_rate,
                "yahoo_ttm_report_currency": yahoo_ttm_report_currency,
                "historical_vs_yahoo_error_pct": historical_error,
                "latest_roll4_vs_direct_error_pct": ticker_validation_error,
                "status": status,
            }
        )

    result = pd.DataFrame(rows)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)

    usable = int((result["status"] == "usable").sum())
    tickers_usable = int(result.loc[result["status"] == "usable", "ticker"].nunique())
    covered = int(result["yahoo_ttm_report_currency"].notna().sum())
    validated_tickers = sum(
        1 for ticker, error in validation_error.items()
        if pd.notna(error) and float(error) <= LATEST_MATCH_TOLERANCE_PCT
    )
    print(
        f"Yahoo historisk EPS-audit: {covered}/{len(result)} rader med rekonstruerad TTM; "
        f"{usable} användbara rader för {tickers_usable} tickers; "
        f"{validated_tickers}/{len(tickers)} tickers har senaste rolling-4 inom "
        f"{LATEST_MATCH_TOLERANCE_PCT:.1f}% från direkt trailingEps."
    )
    return result


if __name__ == "__main__":
    audit()
