from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ROOT
from .fetch_data import load_price_history
from .fundamentals import attach_eps_ttm, load_reports
from .fx import load_fx_history, load_stock_currencies
from .model_data import ensure_gbm_model
from .strategy import run_strategy
from .valuation import GBMModel, calculate_valuation

SOURCE_FILE = ROOT / "data" / "fundamentals" / "eps_ttm_history_enriched.csv"
OUTPUT_FILE = ROOT / "data" / "derived" / "historical_valuation_audit.csv"


def audit(
    source_file: Path = SOURCE_FILE,
    output_file: Path = OUTPUT_FILE,
) -> pd.DataFrame:
    source = pd.read_csv(source_file, encoding="utf-8-sig")
    tickers = sorted(source["ticker"].dropna().astype(str).unique())
    prices = load_price_history()
    reports = load_reports()
    metadata = load_stock_currencies()
    fx = load_fx_history()
    model = GBMModel.load(ensure_gbm_model())

    price_tickers = set(prices["ticker"].astype(str).unique())
    missing_prices = sorted(set(tickers).difference(price_tickers))
    if missing_prices:
        raise ValueError(f"Saknar prisdata för historiska EPS-tickers: {', '.join(missing_prices)}")

    rows: list[dict[str, object]] = []
    for ticker in tickers:
        price = prices.loc[prices["ticker"].astype(str) == ticker].sort_values("date").copy()
        frame = price.rename(
            columns={
                "date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
                "ma200": "MA200",
            }
        )
        mapped = attach_eps_ttm(
            frame,
            ticker,
            reports,
            stock_metadata=metadata,
            fx_history=fx,
        )
        valued = calculate_valuation(mapped, model=model)
        valued["FundamentalLock"] = False
        valued["LockReason"] = ""

        eps_rows = int(pd.to_numeric(valued["EPS_TTM"], errors="coerce").notna().sum())
        pe_rows = int(pd.to_numeric(valued["PE_TTM"], errors="coerce").notna().sum())
        score_mask = pd.to_numeric(valued["Score"], errors="coerce").notna()
        score_rows = int(score_mask.sum())

        strategy = run_strategy(valued, ticker) if score_rows else None
        signals = strategy.get("signals", []) if strategy else []
        executed = [item for item in signals if item.get("status") == "executed"]

        latest = valued.iloc[-1]
        score_dates = valued.loc[score_mask, "Date"]
        rows.append(
            {
                "ticker": ticker,
                "price_rows": len(valued),
                "eps_rows": eps_rows,
                "pe_rows": pe_rows,
                "score_rows": score_rows,
                "first_score_date": pd.Timestamp(score_dates.iloc[0]).date().isoformat() if not score_dates.empty else "",
                "last_score_date": pd.Timestamp(score_dates.iloc[-1]).date().isoformat() if not score_dates.empty else "",
                "latest_eps_raw": pd.to_numeric(pd.Series([latest.get("EPS_TTM_RAW")]), errors="coerce").iloc[0],
                "latest_eps_valuation_currency": pd.to_numeric(pd.Series([latest.get("EPS_TTM")]), errors="coerce").iloc[0],
                "eps_currency": latest.get("EPS_CURRENCY", ""),
                "price_currency": latest.get("PRICE_CURRENCY", ""),
                "latest_fx_rate": pd.to_numeric(pd.Series([latest.get("FX_RATE")]), errors="coerce").iloc[0],
                "latest_pe_ttm": pd.to_numeric(pd.Series([latest.get("PE_TTM")]), errors="coerce").iloc[0],
                "latest_score": pd.to_numeric(pd.Series([latest.get("Score")]), errors="coerce").iloc[0],
                "signals_total": len(signals),
                "signals_executed": len(executed),
                "status": "ready" if score_rows else ("pe_only" if pe_rows else "missing_pe"),
            }
        )
        print(
            f"{ticker}: EPS {eps_rows}, P/E {pe_rows}, score {score_rows}, "
            f"signaler {len(signals)} ({len(executed)} exekverade)"
        )

    audit_frame = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    audit_frame.to_csv(output_file, index=False)

    if (audit_frame["eps_rows"] <= 0).any():
        bad = audit_frame.loc[audit_frame["eps_rows"] <= 0, "ticker"].tolist()
        raise ValueError(f"Ingen point-in-time EPS mappades för: {', '.join(bad)}")
    if (audit_frame["pe_rows"] <= 0).any():
        bad = audit_frame.loc[audit_frame["pe_rows"] <= 0, "ticker"].tolist()
        raise ValueError(f"Ingen P/E kunde beräknas för: {', '.join(bad)}")

    print(
        f"Historisk värderingsaudit klar: {len(audit_frame)} tickers, "
        f"{int((audit_frame['score_rows'] > 0).sum())} med score och "
        f"{int((audit_frame['signals_total'] > 0).sum())} med minst en strategisignal."
    )
    return audit_frame


if __name__ == "__main__":
    audit()
