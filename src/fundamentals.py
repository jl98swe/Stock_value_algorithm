from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT
from .fx import convert_values_to_currency

REPORTS_FILE = ROOT / "data" / "fundamentals" / "reports.csv"
REPORT_COLUMNS = [
    "ticker",
    "period_end",
    "report_period",
    "published_at",
    "effective_date",
    "eps_ttm",
    "source",
    "verified",
    "verified_at",
    "notes",
]


def empty_reports() -> pd.DataFrame:
    return pd.DataFrame(columns=REPORT_COLUMNS)


def _bool_series(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "ja"})


def normalise_reports(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalisera rapporter till projektets point-in-time-schema.

    ``effective_date`` är den första handelsdag då den verifierade EPS-siffran får
    användas av värderingsalgoritmen. Den här modulen försöker därför aldrig
    härleda effective_date från period_end.
    """
    if frame is None or frame.empty:
        return empty_reports()

    result = frame.copy()
    for column in REPORT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    result["ticker"] = result["ticker"].astype("string").str.strip()
    result["report_period"] = result["report_period"].astype("string").str.strip()
    result["source"] = result["source"].astype("string").fillna("")
    result["notes"] = result["notes"].astype("string").fillna("")

    result["period_end"] = pd.to_datetime(result["period_end"], errors="coerce").dt.tz_localize(None)
    result["published_at"] = pd.to_datetime(result["published_at"], errors="coerce", utc=True)
    result["effective_date"] = pd.to_datetime(result["effective_date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    result["verified_at"] = pd.to_datetime(result["verified_at"], errors="coerce", utc=True)
    result["eps_ttm"] = pd.to_numeric(result["eps_ttm"], errors="coerce")
    result["verified"] = _bool_series(result["verified"])

    result = result.dropna(subset=["ticker", "report_period"])
    result = result.loc[result["ticker"].str.len().fillna(0) > 0]
    return (
        result[REPORT_COLUMNS]
        .sort_values(["ticker", "effective_date", "published_at"], na_position="last")
        .drop_duplicates(["ticker", "report_period"], keep="last")
        .reset_index(drop=True)
    )


def load_reports(path: str | Path = REPORTS_FILE) -> pd.DataFrame:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists() or target.stat().st_size == 0:
        return empty_reports()
    return normalise_reports(pd.read_csv(target))


def save_reports(frame: pd.DataFrame, path: str | Path = REPORTS_FILE) -> None:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)

    output = normalise_reports(frame).copy()
    for column in ("period_end", "effective_date"):
        output[column] = output[column].dt.strftime("%Y-%m-%d")
    for column in ("published_at", "verified_at"):
        output[column] = output[column].map(lambda value: value.isoformat() if pd.notna(value) else "")

    temp = target.with_suffix(target.suffix + ".tmp")
    output.to_csv(temp, index=False)
    temp.replace(target)


def verified_reports(frame: pd.DataFrame | None = None) -> pd.DataFrame:
    reports = normalise_reports(frame) if frame is not None else load_reports()
    return reports.loc[
        reports["verified"]
        & reports["effective_date"].notna()
        & reports["eps_ttm"].notna()
    ].copy()


def latest_verified_report(ticker: str, frame: pd.DataFrame | None = None) -> pd.Series | None:
    reports = verified_reports(frame)
    subset = reports.loc[reports["ticker"] == ticker].sort_values(["effective_date", "published_at"])
    return None if subset.empty else subset.iloc[-1]


def _attach_currency_conversion(
    frame: pd.DataFrame,
    ticker: str,
    *,
    date_column: str,
    stock_metadata: pd.DataFrame | None,
    fx_history: pd.DataFrame | None,
) -> pd.DataFrame:
    result = frame.copy()
    result["EPS_TTM_RAW"] = pd.to_numeric(result["EPS_TTM"], errors="coerce")
    result["EPS_CURRENCY"] = pd.NA
    result["PRICE_CURRENCY"] = pd.NA
    result["FX_RATE"] = pd.NA

    # Bakåtkompatibelt API för tester och fristående användning. Produktions-
    # pipelinen skickar alltid metadata + FX explicit och använder då strikt
    # valutakontroll.
    if stock_metadata is None:
        return result

    metadata = stock_metadata.copy()
    if metadata.empty or "ticker" not in metadata.columns:
        result["EPS_TTM"] = pd.NA
        return result

    row = metadata.loc[metadata["ticker"].astype(str) == str(ticker)]
    if row.empty:
        # Ingen gissning: score blockeras tills valuta för tickern finns.
        result["EPS_TTM"] = pd.NA
        return result

    report_currency = str(row.iloc[-1].get("report_currency", "")).strip().upper()
    price_currency = str(row.iloc[-1].get("price_currency", "")).strip().upper()
    result["EPS_CURRENCY"] = report_currency or pd.NA
    result["PRICE_CURRENCY"] = price_currency or pd.NA

    if not report_currency or not price_currency:
        result["EPS_TTM"] = pd.NA
        return result

    if report_currency == price_currency:
        result["FX_RATE"] = 1.0
        result["EPS_TTM"] = result["EPS_TTM_RAW"]
        return result

    if fx_history is None or fx_history.empty:
        result["EPS_TTM"] = pd.NA
        return result

    converted = convert_values_to_currency(
        result,
        value_column="EPS_TTM_RAW",
        date_column=date_column,
        base_currency=report_currency,
        quote_currency=price_currency,
        fx_history=fx_history,
        output_column="EPS_TTM",
        rate_column="FX_RATE",
    )
    return converted


def attach_eps_ttm(
    price_frame: pd.DataFrame,
    ticker: str,
    reports: pd.DataFrame | None = None,
    *,
    stock_metadata: pd.DataFrame | None = None,
    fx_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Lägg point-in-time EPS TTM på varje handelsdag utan look-ahead.

    Endast verifierade rapporter används. EPS börjar gälla på explicit
    ``effective_date`` och forward-fillas därefter. Om produktionspipelinen
    skickar bolagsmetadata konverteras EPS från rapportvaluta till aktiens
    handelsvaluta. Valutaomräkningen använder den senaste fullt avslutade
    FX-dagskursen före respektive handelsdag, så dagens värdering använder
    aldrig en valutastängning som ligger senare samma dag.

    ``EPS_TTM_RAW`` behåller rapporterad EPS i originalvaluta och ``EPS_TTM``
    är värdet som ska användas i P/E-beräkningen.
    """
    result = price_frame.copy()
    date_column = "Date" if "Date" in result.columns else "date"
    if date_column not in result.columns:
        raise ValueError("Prisdata saknar Date/date")

    result[date_column] = pd.to_datetime(result[date_column], errors="coerce").dt.tz_localize(None)
    result = result.sort_values(date_column).reset_index(drop=True)

    verified = verified_reports(reports)
    subset = verified.loc[verified["ticker"] == ticker, ["effective_date", "eps_ttm"]].copy()
    if subset.empty:
        result["EPS_TTM"] = pd.NA
        return _attach_currency_conversion(
            result,
            ticker,
            date_column=date_column,
            stock_metadata=stock_metadata,
            fx_history=fx_history,
        )

    subset = (
        subset.sort_values("effective_date")
        .drop_duplicates("effective_date", keep="last")
        .rename(columns={"effective_date": date_column, "eps_ttm": "EPS_TTM"})
    )
    result = pd.merge_asof(
        result,
        subset,
        on=date_column,
        direction="backward",
        allow_exact_matches=True,
    )
    return _attach_currency_conversion(
        result,
        ticker,
        date_column=date_column,
        stock_metadata=stock_metadata,
        fx_history=fx_history,
    )
