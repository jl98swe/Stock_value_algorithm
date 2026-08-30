from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT
from .fx import convert_values_to_currency, load_fx_history, load_stock_currencies

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
REPORT_DATE_STATE = "report_date_state"
TV_PERIOD_END_STATE = "tv_period_end_state"
TRADINGVIEW_SOURCE_PREFIX = "TradingView /"


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


def valuation_calculation_mode(
    ticker: str,
    frame: pd.DataFrame | None = None,
) -> str:
    """Select TV timing only when the ticker has verified TradingView EPS data."""

    reports = verified_reports(frame)
    subset = reports.loc[reports["ticker"].astype(str) == str(ticker)]
    if subset.empty:
        return REPORT_DATE_STATE
    sources = subset["source"].fillna("").astype(str).str.strip()
    return (
        TV_PERIOD_END_STATE
        if sources.str.startswith(TRADINGVIEW_SOURCE_PREFIX).any()
        else REPORT_DATE_STATE
    )


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

    metadata = load_stock_currencies() if stock_metadata is None else stock_metadata.copy()
    if metadata.empty or "ticker" not in metadata.columns:
        return result

    row = metadata.loc[metadata["ticker"].astype(str) == str(ticker)]
    if row.empty:
        # Metadata byggs successivt när historiska bolag importeras. Fram tills
        # tickern finns där lämnas äldre beteende orört; ingen valuta gissas.
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

    fx = load_fx_history() if fx_history is None else fx_history
    if fx.empty:
        # Fel valuta får aldrig användas som om den vore samma valuta.
        result["EPS_TTM"] = pd.NA
        return result

    return convert_values_to_currency(
        result,
        value_column="EPS_TTM_RAW",
        date_column=date_column,
        base_currency=report_currency,
        quote_currency=price_currency,
        fx_history=fx,
        output_column="EPS_TTM",
        rate_column="FX_RATE",
    )


def attach_eps_ttm(
    price_frame: pd.DataFrame,
    ticker: str,
    reports: pd.DataFrame | None = None,
    *,
    stock_metadata: pd.DataFrame | None = None,
    fx_history: pd.DataFrame | None = None,
    calculation_mode: str = REPORT_DATE_STATE,
) -> pd.DataFrame:
    """Lägg point-in-time EPS TTM på varje handelsdag utan look-ahead.

    Endast verifierade rapporter används. I ``report_date_state`` börjar EPS
    gälla på explicit ``effective_date``. I ``tv_period_end_state`` kopplas
    värdet i stället till ``period_end``, vilket efterliknar TradingViews
    historiska fundamentaldataserie. Rapportdatum används som reserv om
    periodslut saknas. Båda serierna forward-fillas därefter.

    ``EPS_TTM_RAW`` behåller rapporterad EPS i originalvaluta och ``EPS_TTM``
    är det valutajusterade värdet som ska användas i P/E-beräkningen.
    """
    result = price_frame.copy()
    date_column = "Date" if "Date" in result.columns else "date"
    if date_column not in result.columns:
        raise ValueError("Prisdata saknar Date/date")

    result[date_column] = pd.to_datetime(result[date_column], errors="coerce").dt.tz_localize(None)
    result = result.sort_values(date_column).reset_index(drop=True)

    if calculation_mode not in {REPORT_DATE_STATE, TV_PERIOD_END_STATE}:
        raise ValueError(f"Okänt EPS-beräkningsläge: {calculation_mode}")

    verified = verified_reports(reports)
    subset = verified.loc[
        verified["ticker"] == ticker,
        ["period_end", "effective_date", "eps_ttm"],
    ].copy()
    if subset.empty:
        result["EPS_TTM"] = pd.NA
        return _attach_currency_conversion(
            result,
            ticker,
            date_column=date_column,
            stock_metadata=stock_metadata,
            fx_history=fx_history,
        )

    subset["valuation_date"] = subset["effective_date"]
    if calculation_mode == TV_PERIOD_END_STATE:
        subset["valuation_date"] = subset["period_end"].fillna(subset["effective_date"])
    subset = (
        subset.sort_values(["valuation_date", "effective_date"])
        .drop_duplicates("valuation_date", keep="last")
        .rename(columns={"valuation_date": date_column, "eps_ttm": "EPS_TTM"})
        [[date_column, "EPS_TTM"]]
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
