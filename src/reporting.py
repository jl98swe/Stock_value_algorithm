"""Upcoming-report monitoring and realised report-impact export.

The module deliberately keeps Yahoo's generic EPS estimate separate from the
verified diluted quarterly EPS used by the valuation model.  It never turns an
unverified estimate into an EPS TTM or a projected valuation score.
"""

from __future__ import annotations

import argparse
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yfinance as yf

from .config import ROOT
from .events import load_report_calendar
from .manual_eps import find_prior_year_diluted_eps
from .quarterly_eps import DILUTED_METRIC, MANUAL_METRIC, load_quarterly_eps
from .utils import write_json_atomic

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
AUTO_CALENDAR_FILE = ROOT / "data" / "earnings" / "report_calendar.csv"
CALENDAR_HISTORY_FILE = ROOT / "data" / "earnings" / "report_calendar_history.csv"
REPORTS_JSON = ROOT / "docs" / "data" / "reports.json"
METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
REPORT_SOURCE = "Yahoo Finance / calendarEvents"
UNVERIFIED_ESTIMATE_METRIC = "Yahoo EPS Estimate (definition unverified)"
SAFE_ESTIMATE_METRICS = {DILUTED_METRIC, MANUAL_METRIC}
UPCOMING_TRADING_DAYS = 10
URGENT_TRADING_DAYS = 5
RECENT_TRADING_DAYS = 20

CALENDAR_COLUMNS = [
    "ticker",
    "report_date_start",
    "report_date_end",
    "date_status",
    "expected_eps",
    "expected_eps_low",
    "expected_eps_high",
    "expected_eps_currency",
    "expected_eps_metric",
    "expected_eps_verified",
    "source",
    "observed_date",
]


def _resolve(path: str | Path) -> Path:
    target = Path(path)
    return target if target.is_absolute() else ROOT / target


def _bool_series(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "ja"})


def _normalise_calendar(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CALENDAR_COLUMNS)
    result = frame.copy()
    for column in CALENDAR_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[CALENDAR_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype("string").str.strip()
    for column in ("report_date_start", "report_date_end", "observed_date"):
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.tz_localize(None).dt.normalize()
    for column in ("expected_eps", "expected_eps_low", "expected_eps_high"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ("date_status", "expected_eps_currency", "expected_eps_metric", "source"):
        result[column] = result[column].fillna("").astype(str).str.strip()
    result["expected_eps_currency"] = result["expected_eps_currency"].str.upper()
    result["expected_eps_verified"] = _bool_series(result["expected_eps_verified"])
    result = result.dropna(subset=["ticker", "report_date_start", "report_date_end", "observed_date"])
    result = result.loc[result["ticker"].str.len().fillna(0).gt(0)]
    return result.sort_values(["ticker", "report_date_start", "observed_date"]).reset_index(drop=True)


def _concat_frames(frames: list[pd.DataFrame], *, columns: list[str] | None = None) -> pd.DataFrame:
    populated = [frame for frame in frames if frame is not None and not frame.empty]
    if not populated:
        return pd.DataFrame(columns=columns)
    if len(populated) == 1:
        return populated[0].copy()
    return pd.concat(populated, ignore_index=True, sort=False)


def load_auto_report_calendar(path: str | Path = AUTO_CALENDAR_FILE) -> pd.DataFrame:
    target = _resolve(path)
    if not target.exists() or target.stat().st_size == 0:
        return _normalise_calendar(None)
    return _normalise_calendar(pd.read_csv(target))


def save_auto_report_calendar(frame: pd.DataFrame, path: str | Path = AUTO_CALENDAR_FILE) -> None:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    output = _normalise_calendar(frame).copy()
    for column in ("report_date_start", "report_date_end", "observed_date"):
        output[column] = pd.to_datetime(output[column], errors="coerce").dt.strftime("%Y-%m-%d")
    temporary = target.with_suffix(target.suffix + ".tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(target)


def _metadata() -> pd.DataFrame:
    if not METADATA_FILE.exists() or METADATA_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=["ticker", "company", "price_currency", "report_currency"])
    frame = pd.read_csv(METADATA_FILE, encoding="utf-8-sig")
    for column in ("ticker", "company", "price_currency", "report_currency"):
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    frame["price_currency"] = frame["price_currency"].str.upper()
    frame["report_currency"] = frame["report_currency"].str.upper()
    return frame[["ticker", "company", "price_currency", "report_currency"]].drop_duplicates("ticker", keep="last")


def _finite_number(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number) or not math.isfinite(float(number)):
        return None
    return float(number)


def _parse_yahoo_calendar(
    ticker: str,
    payload: dict[str, object] | None,
    *,
    observed_date: object,
    report_currency: str,
) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    raw_dates = payload.get("Earnings Date")
    if raw_dates is None:
        return None
    values = raw_dates if isinstance(raw_dates, (list, tuple, pd.Series, pd.Index)) else [raw_dates]
    dates = sorted(
        {
            pd.Timestamp(value).tz_localize(None).normalize()
            for value in values
            if not pd.isna(pd.to_datetime(value, errors="coerce"))
        }
    )
    if not dates:
        return None
    return {
        "ticker": str(ticker).strip(),
        "report_date_start": dates[0],
        "report_date_end": dates[-1],
        "date_status": "confirmed" if len(dates) == 1 else "estimated_range",
        "expected_eps": _finite_number(payload.get("Earnings Average")),
        "expected_eps_low": _finite_number(payload.get("Earnings Low")),
        "expected_eps_high": _finite_number(payload.get("Earnings High")),
        "expected_eps_currency": str(report_currency or "").strip().upper(),
        "expected_eps_metric": UNVERIFIED_ESTIMATE_METRIC,
        "expected_eps_verified": False,
        "source": REPORT_SOURCE,
        "observed_date": pd.Timestamp(observed_date).tz_localize(None).normalize(),
    }


def _fetch_yahoo_calendar(ticker: str) -> dict[str, object] | None:
    return yf.Ticker(ticker).get_calendar()


def _same_snapshot(left: pd.Series, right: pd.Series) -> bool:
    columns = [column for column in CALENDAR_COLUMNS if column != "observed_date"]
    for column in columns:
        first = left.get(column)
        second = right.get(column)
        first_missing = bool(pd.isna(first))
        second_missing = bool(pd.isna(second))
        if first_missing and second_missing:
            continue
        if first_missing != second_missing:
            return False
        if first != second:
            return False
    return True


def update_report_calendar(
    *,
    workers: int = 2,
    current_path: str | Path = AUTO_CALENDAR_FILE,
    history_path: str | Path = CALENDAR_HISTORY_FILE,
    fetcher: Callable[[str], dict[str, object] | None] = _fetch_yahoo_calendar,
    observed_date: object | None = None,
) -> pd.DataFrame:
    """Update the latest Yahoo calendar while preserving the last good result on failure."""

    metadata = _metadata()
    tickers = metadata["ticker"].loc[metadata["ticker"].str.len().gt(0)].tolist()
    currencies = dict(zip(metadata["ticker"], metadata["report_currency"], strict=False))
    today = (
        pd.Timestamp(observed_date).tz_localize(None).normalize()
        if observed_date is not None
        else pd.Timestamp(datetime.now(STOCKHOLM_TZ).date())
    )
    existing = load_auto_report_calendar(current_path)
    history = load_auto_report_calendar(history_path)
    successful: set[str] = set()
    fetched_rows: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(tickers) or 1))) as executor:
        futures = {executor.submit(fetcher, ticker): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                payload = future.result()
                row = _parse_yahoo_calendar(
                    ticker,
                    payload,
                    observed_date=today,
                    report_currency=currencies.get(ticker, ""),
                )
                if row is None:
                    print(f"INFO {ticker}: Yahoo returnerade inget användbart rapportdatum.")
                    continue
                successful.add(ticker)
                if pd.Timestamp(row["report_date_end"]) >= today:
                    fetched_rows.append(row)
            except Exception as exc:
                print(f"VARNING {ticker}: kommande rapport kunde inte hämtas: {exc}")
            print(f"Rapportkalender {index}/{len(tickers)} klar: {ticker}")

    fetched = _normalise_calendar(pd.DataFrame(fetched_rows, columns=CALENDAR_COLUMNS))
    preserved = existing.loc[~existing["ticker"].isin(successful)].copy()
    current = _normalise_calendar(_concat_frames([preserved, fetched], columns=CALENDAR_COLUMNS))
    current = current.loc[current["report_date_end"] >= today]
    current = current.sort_values(["ticker", "observed_date"]).drop_duplicates("ticker", keep="last")

    additions: list[pd.Series] = []
    for row in fetched.itertuples(index=False):
        item = pd.Series(row._asdict())
        prior = history.loc[history["ticker"] == item["ticker"]].sort_values("observed_date")
        if prior.empty or not _same_snapshot(prior.iloc[-1], item):
            additions.append(item)
    if additions:
        history = _normalise_calendar(
            _concat_frames([history, pd.DataFrame(additions)], columns=CALENDAR_COLUMNS)
        )

    save_auto_report_calendar(current, current_path)
    save_auto_report_calendar(history, history_path)
    print(f"Rapportkalender: {len(current)} kommande datum, {len(history)} sparade ändringspunkter.")
    return current.reset_index(drop=True)


def _json_number(value: object, digits: int = 4) -> float | None:
    number = _finite_number(value)
    return None if number is None else round(number, digits)


def _iso_date(value: object) -> str | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(timestamp) else pd.Timestamp(timestamp).date().isoformat()


def _trading_days_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
    if end <= start:
        return 0
    calendar = xcals.get_calendar("XSTO")
    sessions = calendar.sessions_in_range(start + pd.Timedelta(days=1), end)
    return int(len(sessions))


def _recent_window_start(as_of: pd.Timestamp, sessions: int = RECENT_TRADING_DAYS) -> pd.Timestamp:
    calendar = xcals.get_calendar("XSTO")
    available = calendar.sessions_in_range(as_of - pd.Timedelta(days=max(45, sessions * 3)), as_of)
    if len(available) <= sessions:
        return pd.Timestamp(available[0]) if len(available) else as_of
    return pd.Timestamp(available[-sessions])


def _next_period_end(value: object) -> pd.Timestamp | None:
    current = pd.to_datetime(value, errors="coerce")
    if pd.isna(current):
        return None
    current = pd.Timestamp(current).tz_localize(None).normalize()
    candidate = current + pd.DateOffset(months=3)
    if current.is_month_end:
        candidate = candidate + pd.offsets.MonthEnd(0)
    return pd.Timestamp(candidate).normalize()


def _manual_schedule_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CALENDAR_COLUMNS + ["url", "report_period", "schedule_priority"])
    result = pd.DataFrame(
        {
            "ticker": frame["ticker"],
            "report_date_start": frame["scheduled_at"].map(
                lambda value: pd.Timestamp(value).tz_convert(STOCKHOLM_TZ).date() if pd.notna(value) else pd.NaT
            ),
            "report_date_end": frame["scheduled_at"].map(
                lambda value: pd.Timestamp(value).tz_convert(STOCKHOLM_TZ).date() if pd.notna(value) else pd.NaT
            ),
            "date_status": frame["verified"].map(lambda value: "verified_manual" if value else "manual"),
            "expected_eps": frame["expected_eps"],
            "expected_eps_low": pd.NA,
            "expected_eps_high": pd.NA,
            "expected_eps_currency": frame["expected_eps_currency"],
            "expected_eps_metric": frame["expected_eps_metric"],
            "expected_eps_verified": frame["expected_eps_verified"],
            "source": frame["source"],
            "observed_date": pd.Timestamp(datetime.now(STOCKHOLM_TZ).date()),
            "url": frame["url"],
            "report_period": frame["report_period"],
            "schedule_priority": 0,
        }
    )
    for column in ("report_date_start", "report_date_end", "observed_date"):
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.tz_localize(None).dt.normalize()
    return result.dropna(subset=["ticker", "report_date_start", "report_date_end"])


def _combined_schedule(auto: pd.DataFrame, manual: pd.DataFrame) -> pd.DataFrame:
    automatic = _normalise_calendar(auto).copy()
    automatic["url"] = ""
    automatic["report_period"] = ""
    automatic["schedule_priority"] = 1
    manual_rows = _manual_schedule_rows(manual)
    combined = _concat_frames(
        [manual_rows, automatic],
        columns=CALENDAR_COLUMNS + ["url", "report_period", "schedule_priority"],
    )
    if combined.empty:
        return combined
    combined["ticker"] = combined["ticker"].astype(str).str.strip()
    combined = combined.sort_values(
        ["ticker", "report_date_start", "schedule_priority", "observed_date"],
        ascending=[True, True, True, False],
    )
    return combined.drop_duplicates(["ticker", "report_date_start"], keep="first").reset_index(drop=True)


def _safe_quarter_eps(quarterly: pd.DataFrame, ticker: str, period_end: object) -> pd.Series | None:
    target = pd.to_datetime(period_end, errors="coerce")
    if pd.isna(target) or quarterly.empty:
        return None
    data = quarterly.copy()
    data["period_end"] = pd.to_datetime(data["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["observed_date"] = pd.to_datetime(data["observed_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    data["eps"] = pd.to_numeric(data["eps"], errors="coerce")
    data["_priority"] = data["metric"].map({MANUAL_METRIC: 0, DILUTED_METRIC: 1}).fillna(99)
    subset = data.loc[
        (data["ticker"].astype(str) == str(ticker))
        & data["metric"].isin(SAFE_ESTIMATE_METRICS)
        & data["period_end"].eq(pd.Timestamp(target).tz_localize(None).normalize())
        & data["eps"].notna()
    ]
    return None if subset.empty else subset.sort_values(["_priority", "observed_date"]).iloc[0]


def _meta_maps(metadata: pd.DataFrame) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    names = dict(zip(metadata["ticker"], metadata["company"], strict=False))
    price_currencies = dict(zip(metadata["ticker"], metadata["price_currency"], strict=False))
    report_currencies = dict(zip(metadata["ticker"], metadata["report_currency"], strict=False))
    return names, price_currencies, report_currencies


def _upcoming_rows(
    *,
    schedule: pd.DataFrame,
    reports: pd.DataFrame,
    quarterly: pd.DataFrame,
    valuation_frames: dict[str, pd.DataFrame],
    metadata: pd.DataFrame,
    as_of: pd.Timestamp,
) -> list[dict[str, object]]:
    if schedule.empty:
        return []
    names, price_currencies, report_currencies = _meta_maps(metadata)
    future = schedule.loc[schedule["report_date_end"] >= as_of].copy()
    future["trading_days_to_report"] = future["report_date_start"].map(
        lambda value: _trading_days_between(as_of, pd.Timestamp(value))
    )
    future = future.loc[future["trading_days_to_report"].between(0, UPCOMING_TRADING_DAYS)]
    future = future.sort_values(["report_date_start", "ticker", "schedule_priority"]).drop_duplicates("ticker")

    rows: list[dict[str, object]] = []
    for event in future.itertuples(index=False):
        ticker = str(event.ticker)
        valued = valuation_frames.get(ticker)
        latest = valued.iloc[-1] if valued is not None and not valued.empty else pd.Series(dtype=object)
        ticker_reports = reports.loc[
            (reports["ticker"].astype(str) == ticker)
            & reports["verified"]
            & reports["effective_date"].notna()
            & (reports["effective_date"] <= as_of)
        ].sort_values(["effective_date", "period_end"])
        latest_report = None if ticker_reports.empty else ticker_reports.iloc[-1]
        next_period = _next_period_end(latest_report.get("period_end")) if latest_report is not None else None
        report_start = pd.Timestamp(event.report_date_start)
        period_is_plausible = (
            next_period is not None
            and next_period <= report_start
            and int((report_start - next_period).days) <= 150
        )
        prior = (
            find_prior_year_diluted_eps(ticker, next_period, quarterly)
            if period_is_plausible
            else None
        )
        neutral_status = (
            "available"
            if prior is not None
            else "missing_comparable_diluted_eps"
            if period_is_plausible
            else "report_period_not_safely_inferred"
        )

        expected_verified = bool(event.expected_eps_verified)
        expected_metric = str(event.expected_eps_metric or "")
        expected_comparable = expected_verified and expected_metric in SAFE_ESTIMATE_METRICS
        raw_expected = _finite_number(event.expected_eps)
        estimate_status = (
            "verified_comparable"
            if expected_comparable and raw_expected is not None
            else "unverified_definition"
            if raw_expected is not None
            else "missing"
        )

        rows.append(
            {
                "ticker": ticker,
                "name": names.get(ticker) or ticker.removesuffix(".ST").replace("-", " "),
                "report_date_start": _iso_date(event.report_date_start),
                "report_date_end": _iso_date(event.report_date_end),
                "date_status": str(event.date_status or ""),
                "trading_days_to_report": int(event.trading_days_to_report),
                "urgent": int(event.trading_days_to_report) <= URGENT_TRADING_DAYS,
                "current_price": _json_number(latest.get("Close")),
                "price_currency": price_currencies.get(ticker, "SEK") or "SEK",
                "current_score": _json_number(latest.get("Score")),
                "current_eps_ttm": _json_number(latest.get("EPS_TTM"), 6),
                "eps_ttm_currency": price_currencies.get(ticker, "SEK") or "SEK",
                "next_period_end": _iso_date(next_period) if period_is_plausible else None,
                "neutral_quarter_eps": _json_number(prior.get("eps"), 6) if prior is not None else None,
                "neutral_eps_currency": str(prior.get("eps_currency") or "") if prior is not None else None,
                "neutral_reference_period": _iso_date(prior.get("period_end")) if prior is not None else None,
                "neutral_status": neutral_status,
                "expected_eps": _json_number(raw_expected, 6) if expected_comparable else None,
                "expected_eps_currency": str(event.expected_eps_currency or report_currencies.get(ticker, "")) or None,
                "expected_eps_metric": expected_metric or None,
                "estimate_status": estimate_status,
                "unverified_estimate_available": raw_expected is not None and not expected_comparable,
                "source": str(event.source or ""),
                "url": str(event.url or ""),
            }
        )
    return rows


def _recent_rows(
    *,
    reports: pd.DataFrame,
    quarterly: pd.DataFrame,
    valuation_frames: dict[str, pd.DataFrame],
    metadata: pd.DataFrame,
    as_of: pd.Timestamp,
) -> list[dict[str, object]]:
    names, price_currencies, _ = _meta_maps(metadata)
    start = _recent_window_start(as_of)
    recent = reports.loc[
        reports["verified"]
        & reports["effective_date"].notna()
        & reports["effective_date"].between(start, as_of)
    ].copy()
    recent = recent.sort_values(["ticker", "effective_date", "published_at"]).drop_duplicates(
        ["ticker", "effective_date"], keep="last"
    )

    rows: list[dict[str, object]] = []
    for report in recent.itertuples(index=False):
        ticker = str(report.ticker)
        valued = valuation_frames.get(ticker)
        if valued is None or valued.empty:
            continue
        data = valued.copy()
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce").dt.tz_localize(None).dt.normalize()
        effective = pd.Timestamp(report.effective_date).tz_localize(None).normalize()
        before = data.loc[data["Date"] < effective].tail(1)
        after = data.loc[data["Date"] >= effective].head(1)
        if before.empty or after.empty:
            continue
        before_row = before.iloc[0]
        after_row = after.iloc[0]
        current_quarter = _safe_quarter_eps(quarterly, ticker, report.period_end)
        prior = find_prior_year_diluted_eps(ticker, report.period_end, quarterly)
        price_before = _finite_number(before_row.get("Close"))
        price_after = _finite_number(after_row.get("Close"))
        score_before = _finite_number(before_row.get("Score"))
        score_after = _finite_number(after_row.get("Score"))
        rows.append(
            {
                "ticker": ticker,
                "name": names.get(ticker) or ticker.removesuffix(".ST").replace("-", " "),
                "report_period": str(report.report_period or ""),
                "report_date": _iso_date(effective),
                "period_end": _iso_date(report.period_end),
                "reported_quarter_eps": _json_number(current_quarter.get("eps"), 6) if current_quarter is not None else None,
                "reported_eps_currency": str(current_quarter.get("eps_currency") or "") if current_quarter is not None else None,
                "prior_year_quarter_eps": _json_number(prior.get("eps"), 6) if prior is not None else None,
                "prior_year_eps_currency": str(prior.get("eps_currency") or "") if prior is not None else None,
                "eps_ttm_before": _json_number(before_row.get("EPS_TTM"), 6),
                "eps_ttm_after": _json_number(after_row.get("EPS_TTM"), 6),
                "eps_ttm_currency": price_currencies.get(ticker, "SEK") or "SEK",
                "score_before": _json_number(score_before),
                "score_after": _json_number(score_after),
                "score_change": _json_number(
                    score_after - score_before if score_before is not None and score_after is not None else None
                ),
                "price_before": _json_number(price_before),
                "price_after": _json_number(price_after),
                "price_currency": price_currencies.get(ticker, "SEK") or "SEK",
                "price_change_pct": _json_number(
                    (price_after / price_before - 1.0) * 100.0
                    if price_before not in (None, 0.0) and price_after is not None
                    else None
                ),
                "before_date": _iso_date(before_row.get("Date")),
                "after_date": _iso_date(after_row.get("Date")),
                "source": str(report.source or ""),
                "analysis_status": "reconstructed_current_model",
            }
        )
    return sorted(rows, key=lambda item: (str(item["report_date"]), str(item["ticker"])), reverse=True)


def build_reports_payload(
    *,
    reports: pd.DataFrame,
    valuation_frames: dict[str, pd.DataFrame],
    generated_at: str,
    auto_calendar: pd.DataFrame | None = None,
    manual_calendar: pd.DataFrame | None = None,
    quarterly: pd.DataFrame | None = None,
    output_path: str | Path = REPORTS_JSON,
) -> dict[str, object]:
    metadata = _metadata()
    automatic = load_auto_report_calendar() if auto_calendar is None else _normalise_calendar(auto_calendar)
    manual = load_report_calendar() if manual_calendar is None else manual_calendar.copy()
    quarter_data = load_quarterly_eps() if quarterly is None else quarterly.copy()
    latest_dates = [
        pd.to_datetime(frame["Date"], errors="coerce").max()
        for frame in valuation_frames.values()
        if frame is not None and not frame.empty and "Date" in frame.columns
    ]
    as_of = pd.Timestamp(max(latest_dates)).tz_localize(None).normalize() if latest_dates else pd.Timestamp.now().normalize()
    schedule = _combined_schedule(automatic, manual)
    upcoming = _upcoming_rows(
        schedule=schedule,
        reports=reports,
        quarterly=quarter_data,
        valuation_frames=valuation_frames,
        metadata=metadata,
        as_of=as_of,
    )
    recent = _recent_rows(
        reports=reports,
        quarterly=quarter_data,
        valuation_frames=valuation_frames,
        metadata=metadata,
        as_of=as_of,
    )
    payload = {
        "generated_at": generated_at,
        "as_of_date": as_of.date().isoformat(),
        "upcoming_trading_days": UPCOMING_TRADING_DAYS,
        "urgent_trading_days": URGENT_TRADING_DAYS,
        "recent_trading_days": RECENT_TRADING_DAYS,
        "definitions": {
            "neutral_quarter_eps": (
                "Utspädd EPS för motsvarande rapportperiod föregående år. Samma nivå lämnar EPS TTM "
                "oförändrad; aktiekursen kan ändå ändra värderingspoängen."
            ),
            "expected_eps": (
                "Visas endast när estimatet är verifierat som jämförbar utspädd kvartals-EPS. "
                "Yahoos generella EPS-estimat används inte i strategins TTM-formel."
            ),
            "recent_change": (
                "Före/efter är rekonstruerat med aktuell modell och point-in-time-data. "
                "Scoreförändringen omfattar både ny EPS TTM och kursrörelsen mellan handelsdagarna."
            ),
        },
        "upcoming": upcoming,
        "recent": recent,
    }
    write_json_atomic(_resolve(output_path), payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Uppdatera Yahoo-kalendern för kommande rapporter.")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    update_report_calendar(workers=args.workers)


if __name__ == "__main__":
    main()
