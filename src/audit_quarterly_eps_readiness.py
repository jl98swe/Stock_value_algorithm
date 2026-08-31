from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ROOT
from .fetch_data import load_price_history
from .quarterly_eps import DILUTED_METRIC, load_quarterly_eps

OUT_CSV = ROOT / "data" / "derived" / "quarterly_eps_readiness.csv"
OUT_JSON = ROOT / "data" / "derived" / "quarterly_eps_readiness_summary.json"
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")
NON_QUARTERLY_TICKERS = {"EQT.ST"}
MAX_QUARTER_GAP_DAYS = 150
MAX_LATEST_AGE_DAYS = 150
MIN_FOUR_PERIOD_SPAN_DAYS = 230


def _universe() -> list[str]:
    prices = load_price_history()
    return sorted(prices["ticker"].dropna().astype(str).str.strip().unique().tolist())


def audit_readiness(*, fail_on_missing: bool = True) -> tuple[pd.DataFrame, dict[str, object]]:
    today = pd.Timestamp(datetime.now(STOCKHOLM_TZ).date())
    data = load_quarterly_eps()
    diluted = data.loc[data["metric"].astype(str) == DILUTED_METRIC].copy()
    diluted["period_end"] = pd.to_datetime(diluted["period_end"], errors="coerce").dt.normalize()
    diluted = diluted.dropna(subset=["ticker", "period_end", "eps"])

    rows: list[dict[str, object]] = []
    for ticker in _universe():
        periods = sorted(
            set(
                diluted.loc[diluted["ticker"].astype(str) == ticker, "period_end"]
                .dropna()
                .tolist()
            )
        )
        latest_four = periods[-4:]
        gaps = [int((right - left).days) for left, right in zip(latest_four, latest_four[1:], strict=False)]
        latest_age = int((today - latest_four[-1]).days) if latest_four else None
        span_days = int((latest_four[-1] - latest_four[0]).days) if len(latest_four) == 4 else None
        non_quarterly = ticker in NON_QUARTERLY_TICKERS
        ready = non_quarterly or (
            len(latest_four) == 4
            and bool(gaps)
            and max(gaps) <= MAX_QUARTER_GAP_DAYS
            and span_days is not None
            and span_days >= MIN_FOUR_PERIOD_SPAN_DAYS
            and latest_age is not None
            and latest_age <= MAX_LATEST_AGE_DAYS
        )
        rows.append(
            {
                "ticker": ticker,
                "reporting_mode": "non_quarterly" if non_quarterly else "quarterly",
                "diluted_periods_total": len(periods),
                "latest_period_end": latest_four[-1].date().isoformat() if latest_four else "",
                "latest_age_days": latest_age,
                "latest_four_periods": ";".join(period.date().isoformat() for period in latest_four),
                "latest_four_gaps_days": ";".join(str(gap) for gap in gaps),
                "latest_four_span_days": span_days,
                "ready_for_single_eps_input": ready,
            }
        )

    frame = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    quarterly = frame.loc[frame["reporting_mode"] == "quarterly"]
    missing = quarterly.loc[~quarterly["ready_for_single_eps_input"].astype(bool), "ticker"].astype(str).tolist()
    summary: dict[str, object] = {
        "generated_at": datetime.now(STOCKHOLM_TZ).isoformat(timespec="seconds"),
        "universe_tickers": int(len(frame)),
        "quarterly_tickers": int(len(quarterly)),
        "non_quarterly_tickers": sorted(NON_QUARTERLY_TICKERS.intersection(set(frame["ticker"].astype(str)))),
        "quarterly_ready": int(quarterly["ready_for_single_eps_input"].astype(bool).sum()),
        "quarterly_not_ready": int(len(missing)),
        "not_ready_tickers": missing,
        "criterion": (
            "At least four recent Yahoo diluted EPS periods, maximum gap 150 days, "
            "four-period span at least 230 days, latest period at most 150 days old."
        ),
    }

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"Single-EPS readiness: {summary['quarterly_ready']}/{summary['quarterly_tickers']} "
        "kvartalsrapporterande tickers redo."
    )
    if missing:
        print("Inte redo: " + ", ".join(missing))
        if fail_on_missing:
            raise RuntimeError(
                "Saknar sammanhängande diluted EPS-underlag för: " + ", ".join(missing)
            )
    return frame, summary


def main() -> None:
    audit_readiness(fail_on_missing=True)


if __name__ == "__main__":
    main()
