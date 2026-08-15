from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
YAHOO_TIMESERIES_FILE = ROOT / "data" / "derived" / "yahoo_trailing_eps_timeseries_audit.csv"
OUTPUT_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_aligned.csv"
AUDIT_FILE = ROOT / "data" / "derived" / "eps_alignment_audit.csv"
MAX_PERIOD_END_TO_REPORT_DAYS = 100
YAHOO_SOURCE = "Yahoo Finance / trailingDilutedEPS historical timeseries"
YAHOO_RECONSTRUCTED_SOURCE = (
    "Yahoo Finance / trailingDilutedEPS reconstructed from quarterlyDilutedEPS"
)
FALLBACK_SOURCE = "User-supplied historical EPS TTM fallback"


def _pct_diff(new: float, old: float) -> float:
    denominator = max(abs(float(old)), 1e-9)
    return abs(float(new) - float(old)) / denominator * 100.0


def _load_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Historisk EPS saknar kolumner: {', '.join(missing)}")
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.strip()
    result["report_period"] = result["report_period"].astype(str).str.strip()
    result["report_date"] = pd.to_datetime(result["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["currency"] = result["currency"].astype(str).str.strip().str.upper()
    result = result.dropna(subset=required).copy()
    if result.duplicated(["ticker", "report_period"]).any():
        raise ValueError("Historisk EPS innehåller dubbla ticker + report_period")
    return result.sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)


def _shift_quarter_end(value: pd.Timestamp, quarters: int) -> pd.Timestamp:
    """Flytta ett Yahoo periodslut ett antal kvartal med bibehållen månadsslutlogik."""
    timestamp = pd.Timestamp(value).normalize()
    shifted = timestamp + pd.DateOffset(months=3 * quarters)
    if timestamp.is_month_end:
        shifted = shifted + pd.offsets.MonthEnd(0)
    return pd.Timestamp(shifted).normalize()


def _metric_frame(frame: pd.DataFrame, ticker: str, metric: str) -> pd.DataFrame:
    result = frame.loc[
        (frame["ticker"].astype(str) == ticker)
        & (frame["metric"].astype(str) == metric),
        ["as_of_date", "value", "currency_code"],
    ].copy()
    if result.empty:
        return result
    result["as_of_date"] = pd.to_datetime(result["as_of_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["currency_code"] = result["currency_code"].fillna("").astype(str).str.strip().str.upper()
    return (
        result.dropna(subset=["as_of_date", "value"])
        .sort_values("as_of_date")
        .drop_duplicates("as_of_date", keep="last")
        .reset_index(drop=True)
    )


def _reconstruct_trailing_diluted(
    ticker: str,
    timeseries: pd.DataFrame,
) -> pd.DataFrame:
    """Bygg en så komplett Yahoo diluted-TTM-serie som möjligt.

    Direkt Yahoo trailingDilutedEPS har alltid företräde. Om en enskild
    kvartalspunkt saknas men Yahoo har nästa TTM och de två diluted
    kvartalsvärden som behövs används identiteten:

        TTM_t = TTM_(t+1) - Q_(t+1) + Q_(t-3)

    Motsvarande framåtriktade identitet används också när föregående TTM finns:

        TTM_t = TTM_(t-1) + Q_t - Q_(t-4)

    Endast Yahoo-data i samma valuta kombineras. Rekonstruktionen itereras tills
    inga fler säkra kvartal kan fyllas och märks separat i audit trail.
    """
    trailing = _metric_frame(timeseries, ticker, "trailingDilutedEPS")
    quarterly = _metric_frame(timeseries, ticker, "quarterlyDilutedEPS")
    if trailing.empty:
        return pd.DataFrame(
            columns=["as_of_date", "value", "currency_code", "alignment_status", "eps_source"]
        )

    direct: dict[pd.Timestamp, tuple[float, str]] = {
        pd.Timestamp(row.as_of_date): (float(row.value), str(row.currency_code))
        for row in trailing.itertuples(index=False)
    }
    quarter: dict[pd.Timestamp, tuple[float, str]] = {
        pd.Timestamp(row.as_of_date): (float(row.value), str(row.currency_code))
        for row in quarterly.itertuples(index=False)
    }
    values = dict(direct)
    reconstructed: set[pd.Timestamp] = set()

    # Kandidatperioder är direkta Yahoo-perioder plus kvartalen precis mellan
    # dem. Det gör att exempelvis det systematiskt saknade 2025-Q3 kan byggas
    # utan att hitta på perioder utanför den observerade historiken.
    candidates: set[pd.Timestamp] = set(direct)
    ordered_direct = sorted(direct)
    for left, right in zip(ordered_direct, ordered_direct[1:]):
        cursor = _shift_quarter_end(left, 1)
        while cursor < right and (right - cursor).days <= 370:
            candidates.add(cursor)
            cursor = _shift_quarter_end(cursor, 1)

    for _ in range(8):
        changed = False
        for target in sorted(candidates):
            if target in values:
                continue

            # Baklänges från nästa TTM: TTM_t = TTM_t+1 - Q_t+1 + Q_t-3
            next_date = _shift_quarter_end(target, 1)
            old_quarter_date = _shift_quarter_end(target, -3)
            if next_date in values and next_date in quarter and old_quarter_date in quarter:
                next_ttm, next_currency = values[next_date]
                next_q, next_q_currency = quarter[next_date]
                old_q, old_q_currency = quarter[old_quarter_date]
                if next_currency and next_currency == next_q_currency == old_q_currency:
                    values[target] = (next_ttm - next_q + old_q, next_currency)
                    reconstructed.add(target)
                    changed = True
                    continue

            # Framåt från föregående TTM: TTM_t = TTM_t-1 + Q_t - Q_t-4
            prev_date = _shift_quarter_end(target, -1)
            year_ago_date = _shift_quarter_end(target, -4)
            if prev_date in values and target in quarter and year_ago_date in quarter:
                prev_ttm, prev_currency = values[prev_date]
                current_q, current_q_currency = quarter[target]
                old_q, old_q_currency = quarter[year_ago_date]
                if prev_currency and prev_currency == current_q_currency == old_q_currency:
                    values[target] = (prev_ttm + current_q - old_q, prev_currency)
                    reconstructed.add(target)
                    changed = True

        if not changed:
            break

    rows: list[dict[str, object]] = []
    for as_of_date in sorted(values):
        value, currency = values[as_of_date]
        is_reconstructed = as_of_date in reconstructed
        rows.append(
            {
                "as_of_date": as_of_date,
                "value": float(value),
                "currency_code": currency,
                "alignment_status": (
                    "yahoo_reconstructed_diluted_ttm"
                    if is_reconstructed
                    else "yahoo_trailing_diluted"
                ),
                "eps_source": (
                    YAHOO_RECONSTRUCTED_SOURCE if is_reconstructed else YAHOO_SOURCE
                ),
            }
        )
    return pd.DataFrame(rows)


def _load_yahoo(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = ["ticker", "metric", "as_of_date", "value", "currency_code"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Yahoo-timeseries saknar kolumner: {', '.join(missing)}")

    frame = frame[required].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["metric"] = frame["metric"].astype(str).str.strip()
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["currency_code"] = frame["currency_code"].fillna("").astype(str).str.strip().str.upper()
    frame = frame.dropna(subset=["ticker", "metric", "as_of_date", "value"])

    parts: list[pd.DataFrame] = []
    for ticker in sorted(frame["ticker"].unique()):
        reconstructed = _reconstruct_trailing_diluted(str(ticker), frame)
        if reconstructed.empty:
            continue
        reconstructed.insert(0, "ticker", str(ticker))
        parts.append(reconstructed)
    if not parts:
        return pd.DataFrame(
            columns=["ticker", "as_of_date", "value", "currency_code", "alignment_status", "eps_source"]
        )
    return pd.concat(parts, ignore_index=True).sort_values(["ticker", "as_of_date"]).reset_index(drop=True)


def _map_ticker(history: pd.DataFrame, yahoo: pd.DataFrame) -> dict[int, pd.Series]:
    """Matcha varje rapport mot senaste unika Yahoo-periodslut före rapportdagen.

    Mappingen görs bakifrån så att samma Yahoo-period aldrig kan återanvändas för
    två rapporter. Ett periodslut längre än 100 dagar före rapportdagen accepteras
    inte; då behålls den uppladdade historiska raden som explicit fallback i
    stället för att riskera en kvartalsförskjutning.
    """
    mapping: dict[int, pd.Series] = {}
    if yahoo.empty:
        return mapping

    upper_bound: pd.Timestamp | None = None
    for idx, row in history.sort_values("report_date", ascending=False).iterrows():
        candidates = yahoo.loc[yahoo["as_of_date"] < row["report_date"]].copy()
        if upper_bound is not None:
            candidates = candidates.loc[candidates["as_of_date"] < upper_bound]
        if candidates.empty:
            continue
        best = candidates.sort_values("as_of_date").iloc[-1]
        lag_days = int((pd.Timestamp(row["report_date"]) - pd.Timestamp(best["as_of_date"])).days)
        if lag_days < 0 or lag_days > MAX_PERIOD_END_TO_REPORT_DAYS:
            continue
        mapping[int(idx)] = best
        upper_bound = pd.Timestamp(best["as_of_date"])
    return mapping


def align(
    history_file: Path = HISTORY_FILE,
    yahoo_file: Path = YAHOO_TIMESERIES_FILE,
    output_file: Path = OUTPUT_FILE,
    audit_file: Path = AUDIT_FILE,
) -> pd.DataFrame:
    history = _load_history(history_file)
    yahoo = _load_yahoo(yahoo_file)

    aligned_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []

    for ticker, ticker_history in history.groupby("ticker", sort=True):
        ticker_yahoo = yahoo.loc[yahoo["ticker"] == ticker].copy()
        mapping = _map_ticker(ticker_history, ticker_yahoo)
        for idx, row in ticker_history.iterrows():
            original_eps = float(row["eps_ttm"])
            original_currency = str(row["currency"]).upper()
            mapped = mapping.get(int(idx))

            if mapped is not None:
                yahoo_currency = str(mapped["currency_code"]).upper() or original_currency
                if yahoo_currency and yahoo_currency != original_currency:
                    raise ValueError(
                        f"Yahoo diluted EPS-valuta avviker för {ticker} {row['report_period']}: "
                        f"{yahoo_currency} != {original_currency}"
                    )
                eps_ttm = float(mapped["value"])
                period_end = pd.Timestamp(mapped["as_of_date"])
                source = str(mapped["eps_source"])
                status = str(mapped["alignment_status"])
                lag_days = int((pd.Timestamp(row["report_date"]) - period_end).days)
            else:
                eps_ttm = original_eps
                period_end = pd.NaT
                source = FALLBACK_SOURCE
                status = "fallback_user_history"
                lag_days = np.nan

            aligned_rows.append(
                {
                    "ticker": ticker,
                    "report_period": row["report_period"],
                    "period_end": period_end.date().isoformat() if pd.notna(period_end) else "",
                    "report_date": pd.Timestamp(row["report_date"]).date().isoformat(),
                    "eps_ttm": eps_ttm,
                    "currency": original_currency,
                    "eps_source": source,
                    "alignment_status": status,
                }
            )
            audit_rows.append(
                {
                    "ticker": ticker,
                    "report_period": row["report_period"],
                    "report_date": pd.Timestamp(row["report_date"]).date().isoformat(),
                    "period_end": period_end.date().isoformat() if pd.notna(period_end) else "",
                    "period_end_to_report_days": lag_days,
                    "original_eps_ttm": original_eps,
                    "aligned_eps_ttm": eps_ttm,
                    "currency": original_currency,
                    "abs_change_pct": _pct_diff(eps_ttm, original_eps),
                    "alignment_status": status,
                    "eps_source": source,
                }
            )

    aligned = pd.DataFrame(aligned_rows).sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)
    audit = pd.DataFrame(audit_rows).sort_values(["ticker", "report_date", "report_period"]).reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(output_file, index=False)
    audit.to_csv(audit_file, index=False)

    direct_rows = int((aligned["alignment_status"] == "yahoo_trailing_diluted").sum())
    reconstructed_rows = int((aligned["alignment_status"] == "yahoo_reconstructed_diluted_ttm").sum())
    fallback_rows = int((aligned["alignment_status"] == "fallback_user_history").sum())
    fallback_tickers = int(aligned.loc[aligned["alignment_status"] == "fallback_user_history", "ticker"].nunique())
    materially_changed = int((audit["abs_change_pct"] > 5.0).sum())
    print(
        f"Historisk EPS alignad mot Yahoo diluted EPS: {direct_rows}/{len(aligned)} direkta trailingDilutedEPS, "
        f"{reconstructed_rows} rekonstruerade från Yahoo diluted-komponenter, "
        f"{fallback_rows} fallback-rader i {fallback_tickers} tickers; {materially_changed} rader ändrades >5%."
    )
    if fallback_rows:
        print("Kvarvarande fallback-rader:")
        print(
            aligned.loc[
                aligned["alignment_status"] == "fallback_user_history",
                ["ticker", "report_period", "report_date", "eps_ttm"],
            ].to_string(index=False)
        )
    return aligned


if __name__ == "__main__":
    align()
