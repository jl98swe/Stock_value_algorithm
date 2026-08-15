from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .earnings import latest_earnings
from .fx import convert_values_to_currency, load_fx_history, load_stock_currencies

HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
OUTPUT_FILE = ROOT / "data" / "derived" / "latest_eps_yahoo_comparison.csv"
MATCH_TOLERANCE_PCT = 1.0
NEAR_TOLERANCE_PCT = 5.0


def _relative_error_pct(actual: float, expected: float) -> float:
    denominator = max(abs(float(expected)), 1e-9)
    return abs(float(actual) - float(expected)) / denominator * 100.0


def _converted_history_value(
    value: float,
    observed_date: pd.Timestamp,
    report_currency: str,
    price_currency: str,
    fx: pd.DataFrame,
) -> tuple[float | None, float | None]:
    frame = pd.DataFrame({"date": [observed_date], "value": [value]})
    converted = convert_values_to_currency(
        frame,
        value_column="value",
        date_column="date",
        base_currency=report_currency,
        quote_currency=price_currency,
        fx_history=fx,
        output_column="converted",
        rate_column="fx_rate",
    )
    converted_value = pd.to_numeric(converted.loc[0, "converted"], errors="coerce")
    rate = pd.to_numeric(converted.loc[0, "fx_rate"], errors="coerce")
    return (
        None if pd.isna(converted_value) else float(converted_value),
        None if pd.isna(rate) else float(rate),
    )


def compare(
    history_file: Path = HISTORY_FILE,
    output_file: Path = OUTPUT_FILE,
) -> pd.DataFrame:
    history = pd.read_csv(history_file, encoding="utf-8-sig")
    history["report_date"] = pd.to_datetime(history["report_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    history["eps_ttm"] = pd.to_numeric(history["eps_ttm"], errors="coerce")
    history = (
        history.dropna(subset=["ticker", "report_date", "eps_ttm"])
        .sort_values(["ticker", "report_date", "report_period"])
        .groupby("ticker", as_index=False, sort=True)
        .tail(1)
    )

    yahoo = latest_earnings()
    if yahoo.empty:
        raise ValueError("Yahoo EPS-snapshot är tom. Kör python -m src.earnings först.")

    metadata = load_stock_currencies()
    fx = load_fx_history()
    yahoo = yahoo[["ticker", "report_date", "observed_date", "eps_ttm"]].rename(
        columns={"report_date": "yahoo_report_date", "eps_ttm": "yahoo_eps_ttm"}
    )
    merged = history.merge(yahoo, on="ticker", how="left", validate="one_to_one")
    merged = merged.merge(metadata, on="ticker", how="left", validate="one_to_one")

    rows: list[dict[str, object]] = []
    for row in merged.itertuples(index=False):
        historical_raw = float(row.eps_ttm)
        yahoo_eps = pd.to_numeric(pd.Series([row.yahoo_eps_ttm]), errors="coerce").iloc[0]
        report_currency = str(row.report_currency or row.currency).strip().upper()
        price_currency = str(row.price_currency).strip().upper()
        observed_date = pd.Timestamp(row.observed_date) if pd.notna(row.observed_date) else pd.NaT

        converted_value: float | None = historical_raw if report_currency == price_currency else None
        fx_rate: float | None = 1.0 if report_currency == price_currency else None
        if report_currency != price_currency and pd.notna(observed_date):
            converted_value, fx_rate = _converted_history_value(
                historical_raw,
                pd.Timestamp(observed_date),
                report_currency,
                price_currency,
                fx,
            )

        if pd.isna(yahoo_eps):
            raw_error = np.nan
            converted_error = np.nan
            basis = "missing_yahoo"
            best_error = np.nan
            status = "missing_yahoo"
        else:
            yahoo_value = float(yahoo_eps)
            raw_error = _relative_error_pct(yahoo_value, historical_raw)
            converted_error = (
                _relative_error_pct(yahoo_value, converted_value)
                if converted_value is not None and np.isfinite(converted_value)
                else np.nan
            )

            if report_currency == price_currency:
                basis = "report_currency=price_currency"
                best_error = raw_error
            elif pd.notna(converted_error) and float(converted_error) < raw_error:
                basis = "historical_eps_converted_to_price_currency"
                best_error = float(converted_error)
            else:
                basis = "historical_eps_in_report_currency"
                best_error = raw_error

            if best_error <= MATCH_TOLERANCE_PCT:
                status = "match"
            elif best_error <= NEAR_TOLERANCE_PCT:
                status = "near"
            else:
                status = "mismatch"

        historical_report_date = pd.Timestamp(row.report_date).date().isoformat()
        yahoo_report_date = (
            pd.Timestamp(row.yahoo_report_date).date().isoformat()
            if pd.notna(row.yahoo_report_date)
            else ""
        )
        date_delta_days = (
            abs((pd.Timestamp(row.yahoo_report_date).normalize() - pd.Timestamp(row.report_date).normalize()).days)
            if pd.notna(row.yahoo_report_date)
            else np.nan
        )
        date_status = (
            "match" if pd.notna(date_delta_days) and int(date_delta_days) == 0
            else "near" if pd.notna(date_delta_days) and int(date_delta_days) <= 3
            else "mismatch" if pd.notna(date_delta_days)
            else "missing_yahoo"
        )

        rows.append(
            {
                "ticker": row.ticker,
                "report_period": row.report_period,
                "historical_report_date": historical_report_date,
                "yahoo_report_date": yahoo_report_date,
                "report_date_delta_days": date_delta_days,
                "report_date_status": date_status,
                "historical_eps_raw": historical_raw,
                "report_currency": report_currency,
                "price_currency": price_currency,
                "historical_eps_price_currency": converted_value,
                "comparison_fx_rate": fx_rate,
                "yahoo_eps_ttm": None if pd.isna(yahoo_eps) else float(yahoo_eps),
                "raw_error_pct": raw_error,
                "converted_error_pct": converted_error,
                "comparison_basis": basis,
                "best_error_pct": best_error,
                "value_status": status,
                "yahoo_observed_date": (
                    pd.Timestamp(row.observed_date).date().isoformat()
                    if pd.notna(row.observed_date)
                    else ""
                ),
            }
        )

    result = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_file, index=False)

    fetched = int(result["yahoo_eps_ttm"].notna().sum())
    matches = int(result["value_status"].isin(["match", "near"]).sum())
    exact_dates = int((result["report_date_status"] == "match").sum())
    print(
        f"Yahoo EPS-jämförelse: {fetched}/{len(result)} hämtade, "
        f"{matches}/{len(result)} inom {NEAR_TOLERANCE_PCT:.0f}% mot senaste historiska EPS "
        f"(bästa relevanta valuta), {exact_dates}/{len(result)} exakt samma rapportdatum."
    )
    mismatches = result.loc[result["value_status"] == "mismatch", [
        "ticker", "historical_eps_raw", "historical_eps_price_currency", "yahoo_eps_ttm",
        "comparison_basis", "best_error_pct"
    ]]
    if not mismatches.empty:
        print("Avvikelser över 5%:")
        print(mismatches.to_string(index=False))
    return result


if __name__ == "__main__":
    compare()
