"""Pinned report-day FX fallback; original diluted TTM remains traceable."""
from __future__ import annotations

import math
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

MARKER = "eps_fx_fallback_v1"
MAX_FX_AGE_DAYS = 7


def record_conversion(row, path: Path | None = None) -> None:
    """Append once; later TradingView replacement must not erase the FX audit."""
    from .config import ROOT
    meta = conversion_metadata(row)
    if not meta:
        return
    path = path or ROOT / "data/fundamentals/eps_fx_conversions.csv"
    item = {"ticker": str(row["ticker"]), "report_period": str(row["report_period"]),
            "period_end": str(row["period_end"])[:10], "report_date": meta["report_date"],
            "original_eps_ttm": format(meta["original_eps_ttm"], '.15g'),
            "original_currency": meta["original_currency"], "target_currency": meta["target_currency"],
            "rate": format(meta["rate"], '.15g'), "rate_date": meta["rate_date"],
            "converted_eps_ttm": format(float(row["eps_ttm"]), '.15g'),
            "source": str(row["source"]), "notes": str(row["notes"]),
            "converted_at": str(row.get("verified_at", ""))}
    old = pd.read_csv(path, dtype=str).fillna('') if path.exists() else pd.DataFrame(columns=item)
    keys = [key for key in item if key != "converted_at"]
    if not old.empty and old[keys].eq(pd.Series(item)[keys]).all(axis=1).any():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([old, pd.DataFrame([item])], ignore_index=True).to_csv(path, index=False)


def conversion_metadata(row) -> dict | None:
    if row is None:
        return None
    notes = str(row.get("notes", ""))
    if MARKER not in notes.split("; ") and not notes.startswith(MARKER + ";"):
        return None
    values = dict(re.findall(r"(?:^|;\s*)(fx_[a-z_]+)=([^;]+)", notes))
    try:
        result = {"converted": True, "original_eps_ttm": float(values["fx_original_ttm"]),
                  "original_currency": values["fx_original_currency"],
                  "target_currency": values["fx_target_currency"],
                  "rate": float(values["fx_rate"]), "rate_date": values["fx_date"],
                  "report_date": values["fx_report_date"], "awaiting_tradingview": True}
    except (KeyError, ValueError):
        return None
    return result


def convert_ttm(value: float, currency: str, target: str, report_date, fx: pd.DataFrame) -> dict:
    """Never use the report day's closing FX, or invert an existing SEK TTM."""
    day = pd.Timestamp(report_date).normalize()
    currency, target = currency.upper(), target.upper()
    if currency == target or not math.isfinite(float(value)):
        raise ValueError("Valutaomräkning kräver ett ändligt TTM-värde i annan valuta.")
    data = fx.loc[fx.base_currency.eq(currency) & fx.quote_currency.eq(target)].copy()
    data["date"] = pd.to_datetime(data["date"])
    data["rate"] = pd.to_numeric(data["rate"], errors="coerce")
    data = data.loc[data.date.lt(day) & data.rate.gt(0) & data.rate.map(lambda x: math.isfinite(float(x)))]
    if data.empty:
        raise ValueError(f"Saknar valutakurs före {day.date()} för {currency}/{target}.")
    rate = data.sort_values("date").iloc[-1]
    if (day - rate.date).days > MAX_FX_AGE_DAYS:
        raise ValueError("Senaste valutakurs är för gammal; EPS kompletteras inte.")
    result = float(value) * float(rate.rate)
    if not math.isfinite(result):
        raise ValueError("Omräknad EPS är inte ändlig.")
    notes = (f"{MARKER}; fx_original_ttm={float(value):.15g}; fx_original_currency={currency}; "
             f"fx_target_currency={target}; fx_rate={float(rate.rate):.15g}; "
             f"fx_date={rate.date.date()}; fx_report_date={day.date()}")
    return {"eps_ttm": result, "currency": target, "notes": notes}


def native_ttm(ticker: str, period_end, current_eps: float, currency: str,
               quarterly: pd.DataFrame, earnings: pd.DataFrame, reports: pd.DataFrame) -> dict:
    """Existing quarter bridge, entirely in one currency before any FX."""
    from .manual_eps import find_prior_year_diluted_eps
    from .earnings import EPS_SOURCE
    from .fundamentals import REPORT_CURRENCY_NOTE_PATTERN
    period = pd.Timestamp(period_end).normalize()
    prior = find_prior_year_diluted_eps(ticker, period, quarterly)
    if prior is None or str(prior.eps_currency).upper() != currency:
        raise ValueError("Saknar jämförbar utspädd EPS i samma valuta föregående år.")
    bases = []
    for row in reports.loc[reports.ticker.eq(ticker) & reports.verified].to_dict("records"):
        match = re.search(REPORT_CURRENCY_NOTE_PATTERN, str(row.get("notes", "")))
        conversion = conversion_metadata(row)
        if match and match.group(1).upper() == currency and not str(row["source"]).startswith("Yahoo"):
            bases.append({**row, "priority": 0})
        elif conversion and conversion["original_currency"] == currency:
            bases.append({**row, "eps_ttm": conversion["original_eps_ttm"], "priority": 1})
    for row in earnings.loc[earnings.ticker.eq(ticker) & earnings.eps_currency.eq(currency)
                            & earnings.source.eq(EPS_SOURCE)].to_dict("records"):
        bases.append({**row, "priority": 2})
    eligible = [x for x in bases if pd.notna(x.get("period_end"))
                and 1 <= (period - pd.Timestamp(x["period_end"])).days <= 170
                and pd.notna(x.get("eps_ttm"))]
    if not eligible:
        raise ValueError("Saknar föregående diluted TTM i rapportvalutan.")
    previous = sorted(eligible, key=lambda x: (pd.Timestamp(x["period_end"]), -x["priority"],
                                              str(x.get("observed_date", x.get("verified_at", "")))))[-1]
    value = float(previous["eps_ttm"]) + float(current_eps) - float(prior.eps)
    return {"eps_ttm": value, "notes": (
        f"native_diluted_quarter_bridge; native_base={float(previous['eps_ttm']):.15g}; "
        f"native_base_period={pd.Timestamp(previous['period_end']).date()}; "
        f"native_base_source={previous['source']}; current_diluted_eps={float(current_eps):.15g}; "
        f"prior_year_diluted_eps={float(prior.eps):.15g}")}


def apply_fx_fallbacks(reports: pd.DataFrame, *, today=None) -> pd.DataFrame:
    """Complete newly verified foreign quarters, never replacing manual/TV periods."""
    from .quarterly_eps import load_quarterly_eps, MANUAL_METRIC
    from .earnings import load_earnings_history
    from .fx import load_fx_history, load_stock_currencies
    from .fundamentals import normalise_reports, save_reports
    from .sync_yahoo_eps_reports import _is_replaceable_generated_report

    day = pd.Timestamp(today or datetime.now(ZoneInfo("Europe/Stockholm")).date()).normalize()
    quarterly = load_quarterly_eps()
    current = quarterly.loc[quarterly.metric.eq(MANUAL_METRIC) & quarterly.report_date.le(day)
                            & quarterly.report_date.ge(day - pd.Timedelta(days=140))
                            & quarterly.period_end.le(quarterly.report_date)].copy()
    if current.empty:
        return reports
    current = current.sort_values("period_end").groupby("ticker").tail(1)
    earnings, fx, currencies = load_earnings_history(), load_fx_history(), load_stock_currencies()
    result, changed = reports.copy(), False
    for row in current.itertuples(index=False):
        meta = currencies.loc[currencies.ticker.eq(row.ticker)]
        if meta.empty or row.eps_currency == meta.iloc[-1].price_currency:
            continue
        same = result.loc[result.ticker.eq(row.ticker) & result.period_end.eq(row.period_end)]
        if any(not _is_replaceable_generated_report(x) for _, x in same.iterrows()):
            continue
        try:
            native = native_ttm(row.ticker, row.period_end, row.eps, row.eps_currency, quarterly, earnings, result)
            converted = convert_ttm(native["eps_ttm"], row.eps_currency, meta.iloc[-1].price_currency,
                                    row.report_date, fx)
        except ValueError as error:
            print(f"EPS-omräkning avvaktar för {row.ticker}: {error}")
            continue
        label = f"{row.period_end.year}-Q{row.period_end.quarter}"
        new = dict(ticker=row.ticker, period_end=row.period_end, report_period=label,
                   published_at=pd.NaT, effective_date=row.report_date,
                   eps_ttm=converted["eps_ttm"], source=f"Valutaomräknad diluted EPS TTM / {row.source}",
                   verified=True, verified_at=datetime.now(ZoneInfo("UTC")),
                   notes=f"{converted['notes']}; {native['notes']}; report_currency={converted['currency']}")
        # A generated alias for the same period must not mask the fallback.
        result = result.loc[~(result.ticker.eq(row.ticker) & result.period_end.eq(row.period_end))]
        result = normalise_reports(pd.concat([result, pd.DataFrame([new])], ignore_index=True))
        changed = True
        print(f"EPS valutaomräknad för {row.ticker}: {native['eps_ttm']:.6g} {row.eps_currency} → {converted['eps_ttm']:.6g} {converted['currency']}")
    if changed:
        save_reports(result)
        for row in result.to_dict('records'):
            if conversion_metadata(row):
                record_conversion(row)
    return result
