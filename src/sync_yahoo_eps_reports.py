from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .earnings import EPS_SOURCE, load_earnings_history
from .fundamentals import REPORT_COLUMNS, load_reports, normalise_reports, save_reports
from .fx import load_stock_currencies
from .quarterly_eps import DERIVED_MANUAL_MARKER

AUTO_MARKER = "yahoo_eps_auto_v1"
HISTORICAL_MARKERS = (
    "historical_eps_yahoo_diluted_v2",
    "historical_eps_same_day_policy_v1",
)
MAX_REPORT_LAG_DAYS = 140
MAX_OBSERVED_FALLBACK_LAG_DAYS = 180


def _is_replaceable_generated_report(row: pd.Series) -> bool:
    notes = str(row.get("notes") or "")
    return (
        AUTO_MARKER in notes
        or DERIVED_MANUAL_MARKER in notes
        or any(marker in notes for marker in HISTORICAL_MARKERS)
    )


def _valid_report_date(value: object, period_end: pd.Timestamp) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    report_date = pd.Timestamp(timestamp).tz_localize(None).normalize()
    lag_days = int((report_date - period_end).days)
    if lag_days < 0 or lag_days > MAX_REPORT_LAG_DAYS:
        return None
    return report_date


def _observed_fallback_date(value: object, period_end: pd.Timestamp) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    observed_date = pd.Timestamp(timestamp).tz_localize(None).normalize()
    lag_days = int((observed_date - period_end).days)
    if lag_days < 0 or lag_days > MAX_OBSERVED_FALLBACK_LAG_DAYS:
        return None
    return observed_date


def _new_report_row(
    earning: pd.Series,
    report_period: str,
    *,
    effective_date: pd.Timestamp,
    date_basis: str,
) -> dict[str, object]:
    period_end = pd.Timestamp(earning["period_end"]).normalize()
    observed_date = pd.Timestamp(earning["observed_date"]).normalize()
    currency = str(earning["eps_currency"]).strip().upper()
    return {
        "ticker": str(earning["ticker"]),
        "period_end": period_end,
        "report_period": report_period,
        "published_at": pd.NaT,
        "effective_date": pd.Timestamp(effective_date).normalize(),
        "eps_ttm": float(earning["eps_ttm"]),
        "source": EPS_SOURCE,
        "verified": True,
        "verified_at": datetime.now(timezone.utc),
        "notes": (
            f"{AUTO_MARKER}; metric=trailingDilutedEPS; eps_currency={currency}; "
            f"observed_date={observed_date.date().isoformat()}; "
            f"date_basis={date_basis}; effective_date={pd.Timestamp(effective_date).date().isoformat()}"
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
    earnings = earnings.dropna(subset=["ticker", "period_end", "observed_date", "eps_ttm"])
    earnings = earnings.loc[earnings["eps_currency"].astype(str).str.len() > 0]
    if earnings.empty:
        print("Inga kompletta trailingDilutedEPS-rader att synka.")
        return load_reports()

    metadata = load_stock_currencies()
    metadata_map = metadata.set_index("ticker") if not metadata.empty else pd.DataFrame()
    reports = load_reports()
    eligible_tickers = set(reports["ticker"].astype(str).unique())

    added = 0
    updated = 0
    observed_fallbacks = 0
    skipped_stale = 0
    skipped_currency = 0
    skipped_manual = 0

    earnings = (
        earnings.sort_values(["ticker", "period_end", "observed_date"])
        .drop_duplicates(["ticker", "period_end"], keep="last")
        .reset_index(drop=True)
    )

    for earning in earnings.itertuples(index=False):
        ticker = str(earning.ticker)
        if ticker not in eligible_tickers:
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
        observed_date = pd.Timestamp(earning.observed_date).normalize()
        yahoo_report_date = _valid_report_date(earning.report_date, period_end)
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

            # En manuell kvartals-EPS kan skapa en provisorisk TTM-post på
            # rapportdagen. När Yahoo senare publicerar faktisk trailingDilutedEPS
            # för samma period ersätts bara TTM-värdet/källan; det etablerade
            # effective_date bevaras så att rapportens timing inte flyttas.
            if pd.notna(existing["effective_date"]):
                effective_date = pd.Timestamp(existing["effective_date"]).normalize()
                date_basis = "existing_effective_date"
            elif yahoo_report_date is not None:
                effective_date = yahoo_report_date
                date_basis = "yahoo_report_date"
            else:
                fallback = _observed_fallback_date(observed_date, period_end)
                if fallback is None:
                    skipped_stale += 1
                    continue
                effective_date = fallback
                date_basis = "observed_date_fallback"
                observed_fallbacks += 1

            replacement = _new_report_row(
                earning_series,
                str(existing["report_period"]),
                effective_date=effective_date,
                date_basis=date_basis,
            )
            changed = (
                pd.isna(existing["eps_ttm"])
                or abs(float(existing["eps_ttm"]) - float(replacement["eps_ttm"])) > 1e-12
                or pd.Timestamp(existing["period_end"]).normalize() != period_end
                or str(existing["source"]) != EPS_SOURCE
            )
            if changed:
                for column in REPORT_COLUMNS:
                    reports.at[existing_idx, column] = replacement[column]
                updated += 1
            continue

        if yahoo_report_date is not None:
            same_report_day = ticker_reports.loc[
                ticker_reports["effective_date"].notna()
                & (ticker_reports["effective_date"].dt.normalize() == yahoo_report_date)
                & ticker_reports["period_end"].isna()
            ]
            if not same_report_day.empty:
                existing_idx = same_report_day.index[-1]
                existing = reports.loc[existing_idx]
                if _is_replaceable_generated_report(existing):
                    replacement = _new_report_row(
                        earning_series,
                        str(existing["report_period"]),
                        effective_date=yahoo_report_date,
                        date_basis="yahoo_report_date",
                    )
                    for column in REPORT_COLUMNS:
                        reports.at[existing_idx, column] = replacement[column]
                    updated += 1
                    continue

        known_period_ends = ticker_reports["period_end"].dropna()
        if not known_period_ends.empty and period_end <= known_period_ends.max().normalize():
            skipped_stale += 1
            continue

        if yahoo_report_date is not None:
            effective_date = yahoo_report_date
            date_basis = "yahoo_report_date"
        else:
            fallback = _observed_fallback_date(observed_date, period_end)
            if fallback is None:
                skipped_stale += 1
                print(
                    f"VARNING {ticker}: ny Yahoo-period {period_end.date()} saknar rimligt "
                    "rapport-/observationsdatum; synkas inte."
                )
                continue
            effective_date = fallback
            date_basis = "observed_date_fallback"
            observed_fallbacks += 1
            print(
                f"INFO {ticker}: ny Yahoo-period {period_end.date()} använder observed_date "
                f"{effective_date.date()} eftersom Yahoo rapportdatum saknas/är orimligt."
            )

        new_row = _new_report_row(
            earning_series,
            _auto_period_label(period_end),
            effective_date=effective_date,
            date_basis=date_basis,
        )
        reports = pd.concat([reports, pd.DataFrame([new_row], columns=REPORT_COLUMNS)], ignore_index=True)
        added += 1

    reports = normalise_reports(reports)
    save_reports(reports)
    saved = load_reports()
    print(
        f"Yahoo trailingDilutedEPS -> reports.csv: {added} nya perioder, {updated} uppdaterade, "
        f"{observed_fallbacks} observed-date-fallbacks, {skipped_stale} historiska/stale hoppade över, "
        f"{skipped_currency} valutakonflikter, {skipped_manual} manuella poster bevarade."
    )
    return saved


if __name__ == "__main__":
    sync_yahoo_eps_to_reports()
