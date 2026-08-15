from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .earnings import EPS_SOURCE, load_earnings_history
from .fundamentals import REPORT_COLUMNS, load_reports, normalise_reports, save_reports
from .fx import load_stock_currencies

AUTO_MARKER = "yahoo_eps_auto_v1"
HISTORICAL_MARKERS = (
    "historical_eps_yahoo_diluted_v2",
    "historical_eps_same_day_policy_v1",
)
MAX_REPORT_LAG_DAYS = 140


def _is_replaceable_generated_report(row: pd.Series) -> bool:
    notes = str(row.get("notes") or "")
    return AUTO_MARKER in notes or any(marker in notes for marker in HISTORICAL_MARKERS)


def _new_report_row(earning: pd.Series, report_period: str) -> dict[str, object]:
    period_end = pd.Timestamp(earning["period_end"]).normalize()
    report_date = pd.Timestamp(earning["report_date"]).normalize()
    observed_date = pd.Timestamp(earning["observed_date"]).normalize()
    currency = str(earning["eps_currency"]).strip().upper()
    return {
        "ticker": str(earning["ticker"]),
        "period_end": period_end,
        "report_period": report_period,
        "published_at": pd.NaT,
        "effective_date": report_date,
        "eps_ttm": float(earning["eps_ttm"]),
        "source": EPS_SOURCE,
        "verified": True,
        "verified_at": datetime.now(timezone.utc),
        "notes": (
            f"{AUTO_MARKER}; metric=trailingDilutedEPS; eps_currency={currency}; "
            f"observed_date={observed_date.date().isoformat()}; effective_date=report_date"
        ),
    }


def _auto_period_label(period_end: pd.Timestamp) -> str:
    return f"YAHOO-{pd.Timestamp(period_end).date().isoformat()}"


def sync_yahoo_eps_to_reports() -> pd.DataFrame:
    earnings = load_earnings_history()
    if earnings.empty:
        print("Ingen Yahoo EPS-historik att synka.")
        return load_reports()

    earnings = earnings.loc[earnings["source"].astype(str) == EPS_SOURCE].copy()
    earnings = earnings.dropna(subset=["ticker", "period_end", "report_date", "observed_date", "eps_ttm"])
    earnings = earnings.loc[earnings["eps_currency"].astype(str).str.len() > 0]
    if earnings.empty:
        print("Inga kompletta trailingDilutedEPS-rader med rapportdatum att synka.")
        return load_reports()

    metadata = load_stock_currencies()
    metadata_map = metadata.set_index("ticker") if not metadata.empty else pd.DataFrame()
    reports = load_reports()
    eligible_tickers = set(reports["ticker"].astype(str).unique())

    added = 0
    updated = 0
    skipped_stale = 0
    skipped_currency = 0
    skipped_manual = 0

    # Samma period kan observeras flera gånger vid en Yahoo-korrigering. Sista
    # observationen för perioden vinner, men periodens effective_date förblir
    # rapportdatumet enligt projektets same-day-regel.
    earnings = (
        earnings.sort_values(["ticker", "period_end", "observed_date"])
        .drop_duplicates(["ticker", "period_end"], keep="last")
        .reset_index(drop=True)
    )

    for earning in earnings.itertuples(index=False):
        ticker = str(earning.ticker)
        if ticker not in eligible_tickers:
            # Vi synkar bara bolag som redan har en etablerad historisk
            # fundamentaserie. När nästa historikbatch importeras blir de
            # automatiskt berättigade.
            continue
        if metadata_map.empty or ticker not in metadata_map.index:
            skipped_currency += 1
            print(f"VARNING {ticker}: saknar valutametadata; Yahoo EPS synkas inte.")
            continue

        eps_currency = str(earning.eps_currency).strip().upper()
        report_currency = str(metadata_map.loc[ticker, "report_currency"]).strip().upper()
        if eps_currency != report_currency:
            skipped_currency += 1
            print(
                f"VARNING {ticker}: Yahoo EPS-valuta {eps_currency} != report_currency {report_currency}; "
                "värdet synkas inte."
            )
            continue

        period_end = pd.Timestamp(earning.period_end).normalize()
        report_date = pd.Timestamp(earning.report_date).normalize()
        lag_days = int((report_date - period_end).days)
        if lag_days < 0 or lag_days > MAX_REPORT_LAG_DAYS:
            skipped_stale += 1
            print(
                f"VARNING {ticker}: orimlig period/report-lag {lag_days} dagar "
                f"({period_end.date()} -> {report_date.date()}); synkas inte."
            )
            continue

        ticker_reports = reports.loc[reports["ticker"] == ticker].copy()
        same_period = ticker_reports.loc[
            ticker_reports["period_end"].notna()
            & (ticker_reports["period_end"].dt.normalize() == period_end)
        ]

        earning_series = pd.Series(earning._asdict())
        if not same_period.empty:
            existing_idx = same_period.index[-1]
            existing = reports.loc[existing_idx]
            if not _is_replaceable_generated_report(existing):
                skipped_manual += 1
                continue
            replacement = _new_report_row(earning_series, str(existing["report_period"]))
            changed = (
                pd.isna(existing["eps_ttm"])
                or abs(float(existing["eps_ttm"]) - float(replacement["eps_ttm"])) > 1e-12
                or pd.Timestamp(existing["effective_date"]).normalize() != report_date
                or str(existing["source"]) != EPS_SOURCE
            )
            if changed:
                for column in REPORT_COLUMNS:
                    reports.at[existing_idx, column] = replacement[column]
                updated += 1
            continue

        # Fallback-historik kan sakna period_end. Om Yahoo nu ger samma
        # rapportdatum fyller vi period_end och ersätter EPS med den jämförbara
        # diluted-definitionen i stället för att skapa en dubblett.
        same_report_day = ticker_reports.loc[
            ticker_reports["effective_date"].notna()
            & (ticker_reports["effective_date"].dt.normalize() == report_date)
            & ticker_reports["period_end"].isna()
        ]
        if not same_report_day.empty:
            existing_idx = same_report_day.index[-1]
            existing = reports.loc[existing_idx]
            if _is_replaceable_generated_report(existing):
                replacement = _new_report_row(earning_series, str(existing["report_period"]))
                for column in REPORT_COLUMNS:
                    reports.at[existing_idx, column] = replacement[column]
                updated += 1
                continue

        known_period_ends = ticker_reports["period_end"].dropna()
        if not known_period_ends.empty and period_end <= known_period_ends.max().normalize():
            # Saknar vi en exakt match inne i historiken ska vi inte gissa ett
            # kvartal. Den alignade historiken/fallbacken behålls då orörd.
            skipped_stale += 1
            continue

        new_row = _new_report_row(earning_series, _auto_period_label(period_end))
        reports = pd.concat([reports, pd.DataFrame([new_row], columns=REPORT_COLUMNS)], ignore_index=True)
        added += 1

    reports = normalise_reports(reports)
    save_reports(reports)
    saved = load_reports()
    print(
        f"Yahoo trailingDilutedEPS -> reports.csv: {added} nya perioder, {updated} uppdaterade, "
        f"{skipped_stale} historiska/stale hoppade över, {skipped_currency} valutakonflikter, "
        f"{skipped_manual} manuella poster bevarade."
    )
    return saved


if __name__ == "__main__":
    sync_yahoo_eps_to_reports()
