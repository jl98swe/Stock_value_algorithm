from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ROOT
from .fundamentals import REPORT_COLUMNS, load_reports, save_reports

OVERRIDES_FILE = ROOT / "data" / "fundamentals" / "tradingview_eps_overrides.csv"
HISTORY_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history.csv"
MAPPING_FILE = ROOT / "config" / "ticker_mapping.csv"
MARKER = "tradingview_eps_manual_override_v1"

OVERRIDE_COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency", "source"]
HISTORY_COLUMNS = ["ticker", "report_period", "report_date", "eps_ttm", "currency"]


def _period_end(report_period: str) -> pd.Timestamp:
    year_text, quarter_text = str(report_period).strip().upper().split("-Q", 1)
    year = int(year_text)
    quarter = int(quarter_text)
    month = quarter * 3
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def _load_overrides(path: Path = OVERRIDES_FILE) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in OVERRIDE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"TradingView-overrides saknar kolumner: {', '.join(missing)}")

    frame = frame[OVERRIDE_COLUMNS].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["report_period"] = frame["report_period"].astype(str).str.strip()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.normalize()
    frame["eps_ttm"] = pd.to_numeric(frame["eps_ttm"], errors="coerce")
    frame["currency"] = frame["currency"].astype(str).str.strip().str.upper()
    frame["source"] = frame["source"].astype(str).str.strip()

    required = ["ticker", "report_period", "report_date", "eps_ttm", "currency", "source"]
    if frame[required].isna().any().any():
        raise ValueError("TradingView-overrides innehåller saknade obligatoriska värden")
    if frame.duplicated(["ticker", "report_period"]).any():
        raise ValueError("TradingView-overrides innehåller dubbla ticker + report_period")
    return frame.sort_values(["ticker", "report_period"]).reset_index(drop=True)


def _load_mapping(path: Path = MAPPING_FILE) -> dict[str, str]:
    mapping = pd.read_csv(path, encoding="utf-8-sig")
    required = ["borsdata_ticker", "yahoo_ticker"]
    missing = [column for column in required if column not in mapping.columns]
    if missing:
        raise ValueError(f"Ticker-mappningen saknar kolumner: {', '.join(missing)}")
    mapping = mapping[required].copy()
    mapping["borsdata_ticker"] = mapping["borsdata_ticker"].astype(str).str.strip()
    mapping["yahoo_ticker"] = mapping["yahoo_ticker"].astype(str).str.strip()
    return dict(zip(mapping["borsdata_ticker"], mapping["yahoo_ticker"], strict=False))


def _apply_history(
    overrides: pd.DataFrame,
    path: Path = HISTORY_FILE,
) -> tuple[int, int]:
    history = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in HISTORY_COLUMNS if column not in history.columns]
    if missing:
        raise ValueError(f"EPS-historiken saknar kolumner: {', '.join(missing)}")

    history = history[HISTORY_COLUMNS].copy()
    history["ticker"] = history["ticker"].astype(str).str.strip()
    history["report_period"] = history["report_period"].astype(str).str.strip()

    override_history = overrides[HISTORY_COLUMNS].copy()
    history_currency = {
        (str(row.ticker), str(row.report_period)): str(row.currency).strip().upper()
        for row in history.itertuples(index=False)
    }
    ticker_currencies = (
        history.assign(currency=history["currency"].astype(str).str.strip().str.upper())
        .groupby("ticker")["currency"]
        .agg(lambda values: set(values))
        .to_dict()
    )

    def reference_currency(row: pd.Series) -> str | None:
        ticker = str(row["ticker"])
        period = str(row["report_period"])
        exact = history_currency.get((ticker, period))
        if exact:
            return exact
        known = ticker_currencies.get(ticker, set())
        return next(iter(known)) if len(known) == 1 else None

    compatible = override_history.apply(
        lambda row: (
            reference_currency(row)
            in {None, str(row["currency"]).strip().upper()}
        ),
        axis=1,
    )
    skipped = int((~compatible).sum())
    override_history = override_history.loc[compatible].copy()
    override_keys = pd.MultiIndex.from_frame(override_history[["ticker", "report_period"]])
    history_keys = pd.MultiIndex.from_frame(history[["ticker", "report_period"]])
    history = history.loc[~history_keys.isin(override_keys)].copy()

    merged = pd.concat([history, override_history], ignore_index=True)
    merged["report_date"] = pd.to_datetime(merged["report_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    merged = merged.sort_values(["ticker", "report_period"]).reset_index(drop=True)
    merged.to_csv(path, index=False, encoding="utf-8-sig")
    return len(override_history), skipped


def _apply_reports(overrides: pd.DataFrame, mapping: dict[str, str]) -> None:
    reports = load_reports()
    now = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, object]] = []
    for row in overrides.itertuples(index=False):
        yahoo_ticker = mapping.get(str(row.ticker))
        if not yahoo_ticker:
            raise ValueError(f"Saknar Yahoo-mappning för TradingView-override: {row.ticker}")
        report_date = pd.Timestamp(row.report_date).normalize()
        rows.append(
            {
                "ticker": yahoo_ticker,
                "period_end": _period_end(str(row.report_period)),
                "report_period": str(row.report_period),
                "published_at": pd.NaT,
                "effective_date": report_date,
                "eps_ttm": float(row.eps_ttm),
                "source": str(row.source),
                "verified": True,
                "verified_at": now,
                "notes": (
                    f"{MARKER}; metric=EARNINGS_PER_SHARE_DILUTED TTM; "
                    f"report_currency={row.currency}; effective_date=report_date; "
                    "value manually verified in TradingView"
                ),
            }
        )

    manual = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    override_keys = set(zip(manual["ticker"].astype(str), manual["report_period"].astype(str)))
    keep = ~reports.apply(
        lambda row: (str(row["ticker"]), str(row["report_period"])) in override_keys,
        axis=1,
    )
    combined = pd.concat([reports.loc[keep], manual], ignore_index=True)
    save_reports(combined)


def main() -> None:
    overrides = _load_overrides()
    mapping = _load_mapping()
    history_applied, history_skipped = _apply_history(overrides)
    _apply_reports(overrides, mapping)
    print(
        f"Applicerade {len(overrides)} TradingView EPS TTM-overrides i "
        f"reports.csv; {history_applied} skrevs till {HISTORY_FILE.name} och "
        f"{history_skipped} behöll sin referensvaluta där."
    )


if __name__ == "__main__":
    main()
