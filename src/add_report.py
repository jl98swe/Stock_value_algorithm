from __future__ import annotations

import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from .fundamentals import REPORT_COLUMNS, load_reports, normalise_reports, save_reports

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")


def _same_day_effective_date(published_at: str) -> str:
    timestamp = pd.to_datetime(published_at, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError("published_at är inte en giltig tidpunkt")
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None:
        raise ValueError("published_at måste innehålla tidszon")
    return timestamp.tz_convert(STOCKHOLM_TZ).date().isoformat()


def add_report(
    *,
    ticker: str,
    report_period: str,
    period_end: str,
    published_at: str,
    eps_ttm: float,
    source: str,
    notes: str = "",
    effective_date: str | None = None,
) -> pd.DataFrame:
    """Lägg till eller ersätt en verifierad EPS TTM-post.

    Projektregeln är att en verifierad EPS alltid gäller samma svenska
    kalenderdag som rapporten publiceras. ``effective_date`` härleds därför från
    ``published_at``. Ett explicit effective_date accepteras bara för
    bakåtkompatibilitet och måste då vara exakt samma dag.
    """
    same_day = _same_day_effective_date(published_at)
    if effective_date:
        explicit = pd.to_datetime(effective_date, errors="coerce")
        if pd.isna(explicit) or pd.Timestamp(explicit).date().isoformat() != same_day:
            raise ValueError(
                f"effective_date måste enligt same-day-regeln vara {same_day} "
                f"(svenskt publiceringsdatum)"
            )

    row = pd.DataFrame(
        [
            {
                "ticker": ticker.strip(),
                "period_end": period_end,
                "report_period": report_period.strip(),
                "published_at": published_at,
                "effective_date": same_day,
                "eps_ttm": eps_ttm,
                "source": source.strip(),
                "verified": True,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "notes": notes,
            }
        ],
        columns=REPORT_COLUMNS,
    )
    row = normalise_reports(row)
    if row.empty:
        raise ValueError("Rapportposten kunde inte normaliseras")

    item = row.iloc[0]
    required = ["ticker", "report_period", "period_end", "published_at", "effective_date", "eps_ttm"]
    missing = [column for column in required if pd.isna(item[column])]
    if missing:
        raise ValueError(f"Rapportposten saknar giltiga fält: {', '.join(missing)}")

    existing = load_reports()
    keep = ~(
        (existing["ticker"] == item["ticker"])
        & (existing["report_period"] == item["report_period"])
    )
    combined = pd.concat([existing.loc[keep], row], ignore_index=True)
    save_reports(combined)
    return normalise_reports(combined)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lägg in verifierad EPS TTM. EPS gäller alltid samma svenska dag som publiceringen."
    )
    parser.add_argument("--ticker", required=True, help="Yahoo-ticker, t.ex. ESSITY-B.ST")
    parser.add_argument("--report-period", required=True, help="T.ex. 2026-Q2")
    parser.add_argument("--period-end", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--published-at",
        required=True,
        help="ISO-tid med tidszon, t.ex. 2026-07-17T07:00:00+02:00",
    )
    parser.add_argument(
        "--effective-date",
        required=False,
        default=None,
        help="Valfritt bakåtkompatibelt fält; måste vara samma svenska dag som published_at.",
    )
    parser.add_argument("--eps-ttm", required=True, type=float)
    parser.add_argument("--source", default="Manuellt verifierad bolagsrapport")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    reports = add_report(
        ticker=args.ticker,
        report_period=args.report_period,
        period_end=args.period_end,
        published_at=args.published_at,
        effective_date=args.effective_date,
        eps_ttm=args.eps_ttm,
        source=args.source,
        notes=args.notes,
    )
    latest = reports.loc[
        (reports["ticker"] == args.ticker)
        & (reports["report_period"] == args.report_period)
    ].iloc[-1]
    print(
        f"Sparade {latest['ticker']} {latest['report_period']}: "
        f"EPS TTM {latest['eps_ttm']} från {latest['effective_date'].date()} "
        "(same-day-policy)"
    )


if __name__ == "__main__":
    main()
