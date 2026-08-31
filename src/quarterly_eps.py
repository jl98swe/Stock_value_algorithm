from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .config import ROOT
from .earnings import EPS_SOURCE, load_earnings_history
from .fetch_data import load_price_history
from .utils import write_json_atomic

QUARTERLY_EPS_FILE = ROOT / "data" / "earnings" / "quarterly_eps.csv"
TIMESERIES_AUDIT_FILE = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
COVERAGE_FILE = ROOT / "data" / "derived" / "quarterly_eps_coverage.csv"
COVERAGE_SUMMARY_FILE = ROOT / "data" / "derived" / "quarterly_eps_coverage_summary.json"
QUARTERLY_EPS_JSON = ROOT / "docs" / "data" / "quarterly_eps.json"
METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"

QUARTERLY_COLUMNS = [
    "ticker",
    "period_end",
    "report_date",
    "observed_date",
    "metric",
    "eps",
    "eps_currency",
    "source",
]

DILUTED_METRIC = "quarterlyDilutedEPS"
REPORTED_METRIC = "reportedEPS"
MANUAL_METRIC = "manualDilutedEPS"
DILUTED_SOURCE = "Yahoo Finance / quarterlyDilutedEPS"
REPORTED_SOURCE = "Yahoo Finance / Reported EPS"
DERIVED_MANUAL_MARKER = "manual_quarterly_eps_derived_v1"
METRIC_PRIORITY = {MANUAL_METRIC: 0, DILUTED_METRIC: 1, REPORTED_METRIC: 2}
MAX_REPORT_LAG_DAYS = 120
MAX_PRIOR_YEAR_DISTANCE_DAYS = 21
MAX_PREVIOUS_PERIOD_GAP_DAYS = 170
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")


def _normalise(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=QUARTERLY_COLUMNS)
    result = frame.copy()
    for column in QUARTERLY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[QUARTERLY_COLUMNS].copy()
    result["ticker"] = result["ticker"].astype("string").str.strip()
    result["metric"] = result["metric"].astype("string").str.strip()
    result["source"] = result["source"].astype("string").fillna("").str.strip()
    result["eps_currency"] = result["eps_currency"].astype("string").fillna("").str.strip().str.upper()
    for column in ("period_end", "report_date", "observed_date"):
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["eps"] = pd.to_numeric(result["eps"], errors="coerce")
    result = result.dropna(subset=["ticker", "period_end", "observed_date", "metric", "eps"])
    result = result.loc[
        result["ticker"].str.len().fillna(0).gt(0)
        & result["metric"].isin(METRIC_PRIORITY)
        & result["eps"].map(lambda value: math.isfinite(float(value)))
    ]
    return (
        result.sort_values(["ticker", "period_end", "metric", "observed_date"])
        .drop_duplicates(["ticker", "period_end", "metric"], keep="last")
        .reset_index(drop=True)
    )


def load_quarterly_eps(path: Path = QUARTERLY_EPS_FILE) -> pd.DataFrame:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=QUARTERLY_COLUMNS)
    return _normalise(pd.read_csv(target))


def save_quarterly_eps(frame: pd.DataFrame, path: Path = QUARTERLY_EPS_FILE) -> None:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    output = _normalise(frame).copy()
    for column in ("period_end", "report_date", "observed_date"):
        output[column] = pd.to_datetime(output[column], errors="coerce").dt.strftime("%Y-%m-%d")
    temp = target.with_suffix(target.suffix + ".tmp")
    output.to_csv(temp, index=False)
    temp.replace(target)


def _best_rows(frame: pd.DataFrame) -> pd.DataFrame:
    data = _normalise(frame)
    if data.empty:
        return data
    data = data.copy()
    data["_priority"] = data["metric"].map(METRIC_PRIORITY).fillna(99)
    return (
        data.sort_values(["ticker", "period_end", "_priority", "observed_date"])
        .drop_duplicates(["ticker", "period_end"], keep="first")
        .drop(columns="_priority")
        .reset_index(drop=True)
    )


def _publish_json(frame: pd.DataFrame, coverage_summary: dict[str, object] | None = None) -> None:
    best = _best_rows(frame)
    rows: list[dict[str, object]] = []
    for row in best.itertuples(index=False):
        rows.append(
            {
                "ticker": str(row.ticker),
                "period_end": pd.Timestamp(row.period_end).date().isoformat(),
                "report_date": pd.Timestamp(row.report_date).date().isoformat() if pd.notna(row.report_date) else None,
                "observed_date": pd.Timestamp(row.observed_date).date().isoformat(),
                "metric": str(row.metric),
                "eps": float(row.eps),
                "eps_currency": str(row.eps_currency) or None,
                "source": str(row.source),
            }
        )
    write_json_atomic(
        QUARTERLY_EPS_JSON,
        {
            "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
            "priority": [MANUAL_METRIC, DILUTED_METRIC, REPORTED_METRIC],
            "note": (
                "Manuell verifierad utspädd kvartals-EPS har företräde, därefter Yahoo quarterlyDilutedEPS. "
                "Yahoo Reported EPS används endast som spårbar reserv när diluted-komponenten saknas."
            ),
            "coverage": coverage_summary or {},
            "history": rows,
        },
    )


def _ticker_universe() -> list[str]:
    prices = load_price_history()
    tickers = sorted(prices["ticker"].dropna().astype(str).str.strip().unique().tolist())
    if not tickers:
        raise ValueError("Prisuniversumet innehåller inga tickers.")
    return tickers


def _metadata_currency_map() -> dict[str, str]:
    if not METADATA_FILE.exists() or METADATA_FILE.stat().st_size == 0:
        return {}
    frame = pd.read_csv(METADATA_FILE, encoding="utf-8-sig")
    if "ticker" not in frame.columns or "report_currency" not in frame.columns:
        return {}
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["report_currency"] = frame["report_currency"].fillna("").astype(str).str.strip().str.upper()
    return dict(zip(frame["ticker"], frame["report_currency"], strict=False))


def _parse_quarterly_payload(ticker: str, payload: dict[str, object], observed_date: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for block in (payload.get("timeseries") or {}).get("result") or []:
        values = block.get(DILUTED_METRIC)
        if not isinstance(values, list):
            continue
        block_currency = str((block.get("meta") or {}).get("currencyCode") or "").strip().upper()
        for item in values:
            raw = pd.to_numeric((item.get("reportedValue") or {}).get("raw"), errors="coerce")
            period_end = pd.to_datetime(item.get("asOfDate"), errors="coerce")
            if pd.isna(raw) or pd.isna(period_end) or not math.isfinite(float(raw)):
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "period_end": pd.Timestamp(period_end).tz_localize(None).normalize(),
                    "report_date": pd.NaT,
                    "observed_date": observed_date,
                    "metric": DILUTED_METRIC,
                    "eps": float(raw),
                    "eps_currency": str(item.get("currencyCode") or block_currency or "").strip().upper(),
                    "source": DILUTED_SOURCE,
                }
            )
    return rows


def _fetch_recent_one(ticker: str, observed_date: str) -> list[dict[str, object]]:
    now = datetime.now(STOCKHOLM_TZ)
    period1 = int((now - timedelta(days=900)).timestamp())
    period2 = int((now + timedelta(days=2)).timestamp())
    url = (
        f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}"
        f"?symbol={ticker}&type={DILUTED_METRIC}&period1={period1}&period2={period2}"
    )
    try:
        response = yf.Ticker(ticker)._data.cache_get(url=url)
        payload = json.loads(response.text)
        return _parse_quarterly_payload(ticker, payload, observed_date)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo {DILUTED_METRIC} kunde inte hämtas: {exc}")
        return []


def update_recent(*, workers: int = 4) -> pd.DataFrame:
    tickers = _ticker_universe()
    observed_date = datetime.now(STOCKHOLM_TZ).date().isoformat()
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {executor.submit(_fetch_recent_one, ticker, observed_date): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                print(f"VARNING {ticker}: kvartals-EPS-hämtningen misslyckades: {exc}")
            print(f"Kvartals-EPS {index}/{len(tickers)} klar: {ticker}")

    fetched = _normalise(pd.DataFrame(rows, columns=QUARTERLY_COLUMNS))
    if fetched.empty:
        raise RuntimeError(f"Yahoo returnerade ingen {DILUTED_METRIC} för någon ticker.")
    existing = load_quarterly_eps()
    combined = _normalise(pd.concat([existing, fetched], ignore_index=True))
    save_quarterly_eps(combined)
    _publish_json(combined)
    covered = fetched["ticker"].nunique()
    print(f"Yahoo aktuell kvartals-EPS: {len(fetched)} perioder för {covered}/{len(tickers)} tickers.")
    return combined


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


def _fetch_reported_one(ticker: str) -> list[tuple[pd.Timestamp, float]]:
    try:
        frame = yf.Ticker(ticker).get_earnings_dates(limit=100, offset=1)
    except Exception as exc:
        print(f"VARNING {ticker}: Yahoo Reported EPS kunde inte hämtas: {exc}")
        return []
    if frame is None or frame.empty:
        return []

    eps_column = "Reported EPS" if "Reported EPS" in frame.columns else None
    if eps_column is None:
        return []
    now_utc = pd.Timestamp.now(tz="UTC")
    rows: list[tuple[pd.Timestamp, float]] = []
    for index, row in frame.iterrows():
        timestamp = pd.to_datetime(index, errors="coerce")
        eps = pd.to_numeric(row.get(eps_column), errors="coerce")
        if pd.isna(timestamp) or pd.isna(eps) or not math.isfinite(float(eps)):
            continue
        timestamp = pd.Timestamp(timestamp)
        comparison = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        if comparison > now_utc:
            continue
        local_date = _stockholm_date(timestamp)
        if local_date is not None:
            rows.append((local_date, float(eps)))
    return sorted(rows, key=lambda item: item[0])


def _map_reported_to_periods(
    period_ends: list[pd.Timestamp],
    reported: list[tuple[pd.Timestamp, float]],
) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    periods = sorted({pd.Timestamp(value).normalize() for value in period_ends})
    used: set[pd.Timestamp] = set()
    result: list[tuple[pd.Timestamp, pd.Timestamp, float]] = []
    for index, period_end in enumerate(periods):
        next_period = periods[index + 1] if index + 1 < len(periods) else None
        candidates: list[tuple[pd.Timestamp, float]] = []
        for report_date, eps in reported:
            report_date = pd.Timestamp(report_date).normalize()
            lag = int((report_date - period_end).days)
            if report_date in used or lag < 0 or lag > MAX_REPORT_LAG_DAYS:
                continue
            if next_period is not None and report_date >= next_period:
                continue
            candidates.append((report_date, eps))
        if candidates:
            report_date, eps = min(candidates, key=lambda item: item[0])
            used.add(report_date)
            result.append((period_end, report_date, float(eps)))
    return result


def _build_coverage(
    tickers: list[str],
    audit: pd.DataFrame,
    quarterly: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    best = _best_rows(quarterly)
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        trailing_periods = set(
            pd.to_datetime(
                audit.loc[
                    (audit["ticker"].astype(str) == ticker)
                    & (audit["metric"].astype(str) == "trailingDilutedEPS"),
                    "as_of_date",
                ],
                errors="coerce",
            ).dropna().dt.normalize()
        )
        ticker_best = best.loc[best["ticker"].astype(str) == ticker]
        covered_periods = set(pd.to_datetime(ticker_best["period_end"], errors="coerce").dropna().dt.normalize())
        relevant_covered = trailing_periods.intersection(covered_periods)
        missing = sorted(trailing_periods.difference(covered_periods))
        ticker_all = quarterly.loc[quarterly["ticker"].astype(str) == ticker]
        rows.append(
            {
                "ticker": ticker,
                "trailing_periods": len(trailing_periods),
                "quarterly_diluted_periods": int((ticker_all["metric"] == DILUTED_METRIC).sum()),
                "reported_eps_periods": int((ticker_all["metric"] == REPORTED_METRIC).sum()),
                "manual_eps_periods": int((ticker_all["metric"] == MANUAL_METRIC).sum()),
                "covered_trailing_periods": len(relevant_covered),
                "missing_trailing_periods": len(missing),
                "coverage_pct": round((100.0 * len(relevant_covered) / len(trailing_periods)), 2) if trailing_periods else 0.0,
                "missing_period_ends": ";".join(value.date().isoformat() for value in missing),
            }
        )
    coverage = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    total_trailing = int(coverage["trailing_periods"].sum()) if not coverage.empty else 0
    total_covered = int(coverage["covered_trailing_periods"].sum()) if not coverage.empty else 0
    summary: dict[str, object] = {
        "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
        "universe_tickers": len(tickers),
        "tickers_with_any_eps": int(best["ticker"].nunique()) if not best.empty else 0,
        "tickers_with_full_trailing_coverage": int((coverage["missing_trailing_periods"] == 0).sum()) if not coverage.empty else 0,
        "tickers_with_missing_trailing_periods": int((coverage["missing_trailing_periods"] > 0).sum()) if not coverage.empty else 0,
        "trailing_periods": total_trailing,
        "covered_trailing_periods": total_covered,
        "coverage_pct": round((100.0 * total_covered / total_trailing), 2) if total_trailing else 0.0,
        "tickers_without_any_eps": sorted(set(tickers).difference(set(best["ticker"].astype(str)))) if not best.empty else tickers,
    }
    return coverage, summary


def backfill_from_audit(*, workers: int = 4) -> pd.DataFrame:
    if not TIMESERIES_AUDIT_FILE.exists() or TIMESERIES_AUDIT_FILE.stat().st_size == 0:
        raise FileNotFoundError(f"Saknar {TIMESERIES_AUDIT_FILE}")
    audit = pd.read_csv(TIMESERIES_AUDIT_FILE)
    required = {"ticker", "metric", "as_of_date", "value", "currency_code"}
    missing = sorted(required.difference(audit.columns))
    if missing:
        raise ValueError(f"Yahoo-audit saknar kolumner: {', '.join(missing)}")
    tickers = _ticker_universe()
    observed_date = datetime.now(STOCKHOLM_TZ).date().isoformat()

    diluted = audit.loc[audit["metric"].astype(str) == DILUTED_METRIC].copy()
    diluted_rows = pd.DataFrame(
        {
            "ticker": diluted["ticker"],
            "period_end": diluted["as_of_date"],
            "report_date": pd.NaT,
            "observed_date": observed_date,
            "metric": DILUTED_METRIC,
            "eps": diluted["value"],
            "eps_currency": diluted["currency_code"],
            "source": DILUTED_SOURCE,
        }
    )

    reported_map: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as executor:
        futures = {executor.submit(_fetch_reported_one, ticker): ticker for ticker in tickers}
        for index, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                reported_map[ticker] = future.result()
            except Exception as exc:
                print(f"VARNING {ticker}: Reported EPS-hämtningen misslyckades: {exc}")
                reported_map[ticker] = []
            print(f"Yahoo Reported EPS {index}/{len(tickers)} klar: {ticker}")

    currency_map = _metadata_currency_map()
    reported_rows: list[dict[str, object]] = []
    for ticker in tickers:
        period_ends = pd.to_datetime(
            audit.loc[
                (audit["ticker"].astype(str) == ticker)
                & (audit["metric"].astype(str) == "trailingDilutedEPS"),
                "as_of_date",
            ],
            errors="coerce",
        ).dropna().dt.normalize().tolist()
        for period_end, report_date, eps in _map_reported_to_periods(period_ends, reported_map.get(ticker, [])):
            reported_rows.append(
                {
                    "ticker": ticker,
                    "period_end": period_end,
                    "report_date": report_date,
                    "observed_date": observed_date,
                    "metric": REPORTED_METRIC,
                    "eps": eps,
                    "eps_currency": currency_map.get(ticker, ""),
                    "source": REPORTED_SOURCE,
                }
            )

    existing = load_quarterly_eps()
    new_rows = _normalise(
        pd.concat(
            [
                diluted_rows,
                pd.DataFrame(reported_rows, columns=QUARTERLY_COLUMNS),
            ],
            ignore_index=True,
        )
    )
    combined = _normalise(pd.concat([existing, new_rows], ignore_index=True))
    save_quarterly_eps(combined)

    coverage, summary = _build_coverage(tickers, audit, combined)
    COVERAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(COVERAGE_FILE, index=False)
    COVERAGE_SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _publish_json(combined, summary)

    print(
        f"Kvartals-EPS backfill: {summary['tickers_with_any_eps']}/{summary['universe_tickers']} tickers med data, "
        f"{summary['covered_trailing_periods']}/{summary['trailing_periods']} historiska TTM-perioder har en "
        f"kvartalskomponent ({summary['coverage_pct']}%)."
    )
    return combined


def _target_prior_year(period_end: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(period_end).normalize()
    target = timestamp - pd.DateOffset(years=1)
    if timestamp.is_month_end:
        target = target + pd.offsets.MonthEnd(0)
    return pd.Timestamp(target).normalize()


def find_prior_year_eps(
    ticker: str,
    period_end: object,
    frame: pd.DataFrame | None = None,
) -> pd.Series | None:
    data = _normalise(frame) if frame is not None else load_quarterly_eps()
    if data.empty:
        return None
    target = _target_prior_year(pd.Timestamp(period_end))
    subset = data.loc[data["ticker"].astype(str) == str(ticker)].copy()
    if subset.empty:
        return None
    subset["distance_days"] = (subset["period_end"] - target).abs().dt.days
    subset = subset.loc[subset["distance_days"] <= MAX_PRIOR_YEAR_DISTANCE_DAYS].copy()
    if subset.empty:
        return None
    subset["metric_priority"] = subset["metric"].map(METRIC_PRIORITY).fillna(99)
    return subset.sort_values(["distance_days", "metric_priority", "observed_date"]).iloc[0]


def _normalise_earnings_for_derivation(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None:
        return load_earnings_history()
    result = frame.copy()
    for column in ["ticker", "period_end", "observed_date", "eps_ttm", "eps_currency", "source"]:
        if column not in result.columns:
            result[column] = pd.NA
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["period_end"] = pd.to_datetime(result["period_end"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["observed_date"] = pd.to_datetime(result["observed_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["eps_currency"] = result["eps_currency"].fillna("").astype(str).str.strip().str.upper()
    result["source"] = result["source"].fillna("").astype(str).str.strip()
    return result


def derive_manual_eps_ttm(
    *,
    ticker: str,
    period_end: object,
    current_quarter_eps: float,
    quarterly_frame: pd.DataFrame | None = None,
    earnings_frame: pd.DataFrame | None = None,
) -> dict[str, object]:
    period = pd.to_datetime(period_end, errors="coerce")
    if pd.isna(period):
        raise ValueError("period_end är inte ett giltigt datum")
    period = pd.Timestamp(period).tz_localize(None).normalize()
    current_eps = float(current_quarter_eps)
    if not math.isfinite(current_eps):
        raise ValueError("EPS måste vara ett ändligt tal")

    prior = find_prior_year_eps(ticker, period, quarterly_frame)
    if prior is None:
        target = _target_prior_year(period).date().isoformat()
        raise ValueError(
            f"Saknar sparad EPS för {ticker} omkring motsvarande kvartal {target}. "
            "TTM härleds inte genom gissning."
        )

    earnings = _normalise_earnings_for_derivation(earnings_frame)
    subset = earnings.loc[
        (earnings["ticker"].astype(str) == str(ticker))
        & (earnings["source"].astype(str) == EPS_SOURCE)
        & earnings["period_end"].notna()
        & (earnings["period_end"] < period)
        & earnings["eps_ttm"].notna()
        & earnings["eps_currency"].astype(str).str.len().gt(0)
    ].copy()
    if subset.empty:
        raise ValueError(
            f"Saknar föregående Yahoo trailingDilutedEPS för {ticker}; kan inte härleda ny TTM säkert."
        )
    previous = subset.sort_values(["period_end", "observed_date"]).iloc[-1]
    gap_days = int((period - pd.Timestamp(previous["period_end"]).normalize()).days)
    if gap_days <= 0 or gap_days > MAX_PREVIOUS_PERIOD_GAP_DAYS:
        raise ValueError(
            f"Föregående Yahoo TTM-period för {ticker} ligger {gap_days} dagar från nya perioden; "
            "automatisk härledning stoppas."
        )

    previous_currency = str(previous["eps_currency"] or "").strip().upper()
    prior_currency = str(prior["eps_currency"] or "").strip().upper()
    if prior_currency and previous_currency and prior_currency != previous_currency:
        raise ValueError(
            f"Valutakonflikt för {ticker}: föregående TTM är {previous_currency}, "
            f"föregående års kvartals-EPS är {prior_currency}."
        )
    currency = previous_currency or prior_currency
    if not currency:
        raise ValueError(f"Saknar EPS-valuta för {ticker}; TTM härleds inte.")

    previous_ttm = float(previous["eps_ttm"])
    prior_eps = float(prior["eps"])
    derived_ttm = previous_ttm + current_eps - prior_eps
    if not math.isfinite(derived_ttm):
        raise ValueError("Härledd EPS TTM blev inte ett ändligt tal")

    audit_note = (
        f"{DERIVED_MANUAL_MARKER}; previous_ttm={previous_ttm:.12g}; "
        f"previous_period_end={pd.Timestamp(previous['period_end']).date().isoformat()}; "
        f"current_quarter_eps={current_eps:.12g}; prior_year_eps={prior_eps:.12g}; "
        f"prior_year_period_end={pd.Timestamp(prior['period_end']).date().isoformat()}; "
        f"prior_year_metric={prior['metric']}; report_currency={currency}"
    )
    return {
        "eps_ttm": float(derived_ttm),
        "eps_currency": currency,
        "previous_ttm": previous_ttm,
        "previous_period_end": pd.Timestamp(previous["period_end"]).normalize(),
        "prior_year_eps": prior_eps,
        "prior_year_period_end": pd.Timestamp(prior["period_end"]).normalize(),
        "prior_year_metric": str(prior["metric"]),
        "audit_note": audit_note,
    }


def upsert_manual_quarterly_eps(
    *,
    ticker: str,
    period_end: object,
    report_date: object,
    eps: float,
    eps_currency: str,
    source: str,
    path: Path = QUARTERLY_EPS_FILE,
) -> pd.DataFrame:
    observed_date = datetime.now(STOCKHOLM_TZ).date().isoformat()
    row = pd.DataFrame(
        [
            {
                "ticker": str(ticker).strip(),
                "period_end": period_end,
                "report_date": report_date,
                "observed_date": observed_date,
                "metric": MANUAL_METRIC,
                "eps": float(eps),
                "eps_currency": str(eps_currency).strip().upper(),
                "source": str(source).strip(),
            }
        ],
        columns=QUARTERLY_COLUMNS,
    )
    existing = load_quarterly_eps(path)
    combined = _normalise(pd.concat([existing, row], ignore_index=True))
    save_quarterly_eps(combined, path)
    if Path(path).resolve() == QUARTERLY_EPS_FILE.resolve():
        _publish_json(combined)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Hämta och lagra kvartals-EPS från Yahoo för hela aktieuniversumet.")
    parser.add_argument("--backfill", action="store_true", help="Bygg historik från färsk Yahoo-audit och Reported EPS.")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.backfill:
        backfill_from_audit(workers=args.workers)
    else:
        update_recent(workers=args.workers)


if __name__ == "__main__":
    main()
