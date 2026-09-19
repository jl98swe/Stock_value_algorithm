from __future__ import annotations

import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from .fundamentals import REPORT_COLUMNS, load_reports, normalise_reports, save_reports
from .fx import load_stock_currencies
from .manual_eps import derive_manual_eps_ttm_safe
from .manual_reports import append_manual_submission, publish_manual_reports
from .quarterly_eps import upsert_manual_quarterly_eps

STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")


def _same_day_effective_date(published_at: str) -> str:
    value = str(published_at).strip()
    if len(value) == 10:
        date_value = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
        if pd.notna(date_value):
            return pd.Timestamp(date_value).date().isoformat()
    timestamp = pd.to_datetime(published_at, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError("published_at är inte ett giltigt datum eller en giltig tidpunkt")
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None:
        raise ValueError("en tidpunkt i published_at måste innehålla tidszon")
    return timestamp.tz_convert(STOCKHOLM_TZ).date().isoformat()


def add_report(
    *,
    ticker: str,
    report_period: str,
    period_end: str,
    published_at: str,
    source: str,
    notes: str = "",
    effective_date: str | None = None,
    eps: float | None = None,
    eps_ttm: float | None = None,
) -> pd.DataFrame:
    """Lägg till eller ersätt en manuellt registrerad rapportpost.

    Normalvägen tar endast periodens utspädda EPS. Ny TTM härleds från föregående
    Yahoo trailingDilutedEPS och motsvarande utspädda period-EPS ett år tidigare::

        ny_TTM = föregående_TTM + aktuell_period_EPS - EPS_samma_period_fjol

    Endast manuellt verifierad utspädd EPS eller Yahoo quarterlyDilutedEPS får
    användas för jämförelseperioden. Yahoo Reported EPS används inte i formeln,
    eftersom dess definition kan skilja sig från diluted EPS.
    """
    if (eps is None) == (eps_ttm is None):
        raise ValueError("Ange exakt ett av eps (period-EPS) eller eps_ttm")

    same_day = _same_day_effective_date(published_at)
    if effective_date:
        explicit = pd.to_datetime(effective_date, errors="coerce")
        if pd.isna(explicit) or pd.Timestamp(explicit).date().isoformat() != same_day:
            raise ValueError(
                f"effective_date måste enligt same-day-regeln vara {same_day} "
                f"(svenskt publiceringsdatum)"
            )

    derivation: dict[str, object] | None = None
    user_notes = str(notes or "").strip()
    final_notes = user_notes
    final_eps_ttm: float
    eps_currency: str
    input_metric: str
    if eps is not None:
        derivation = derive_manual_eps_ttm_safe(
            ticker=ticker.strip(),
            period_end=period_end,
            current_period_eps=float(eps),
        )
        final_eps_ttm = float(derivation["eps_ttm"])
        eps_currency = str(derivation["eps_currency"])
        input_metric = "quarterly_eps"
        derivation_note = str(derivation["audit_note"])
        final_notes = f"{final_notes}; {derivation_note}" if final_notes else derivation_note
    else:
        final_eps_ttm = float(eps_ttm)
        currencies = load_stock_currencies()
        match = currencies.loc[currencies["ticker"] == ticker.strip(), "report_currency"]
        if match.empty or not str(match.iloc[-1]).strip():
            raise ValueError(f"Rapportvaluta saknas för {ticker.strip()}")
        eps_currency = str(match.iloc[-1]).strip().upper()
        input_metric = "eps_ttm"

    audit_marker = (
        f"manual_report_submission_v1; input_metric={input_metric}; "
        f"report_currency={eps_currency}"
    )
    final_notes = f"{final_notes}; {audit_marker}" if final_notes else audit_marker

    row = pd.DataFrame(
        [
            {
                "ticker": ticker.strip(),
                "period_end": period_end,
                "report_period": report_period.strip(),
                "published_at": published_at,
                "effective_date": same_day,
                "eps_ttm": final_eps_ttm,
                "source": source.strip(),
                "verified": True,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "notes": final_notes,
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

    if eps is not None and derivation is not None:
        upsert_manual_quarterly_eps(
            ticker=ticker.strip(),
            period_end=period_end,
            report_date=same_day,
            eps=float(eps),
            eps_currency=str(derivation["eps_currency"]),
            source=source.strip(),
        )

    append_manual_submission(
        ticker=ticker.strip(),
        report_period=report_period.strip(),
        period_end=period_end,
        published_at=published_at,
        effective_date=same_day,
        input_metric=input_metric,
        input_eps=float(eps if eps is not None else eps_ttm),
        result_eps_ttm=final_eps_ttm,
        eps_currency=eps_currency,
        source=source.strip(),
        notes=user_notes,
    )
    publish_manual_reports(combined)

    return normalise_reports(combined)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Lägg in EPS TTM direkt eller utspädd EPS för rapportperioden. Ett kvartalsvärde "
            "räknas om till EPS TTM från sparad historik."
        )
    )
    parser.add_argument("--ticker", required=True, help="Yahoo-ticker, t.ex. ESSITY-B.ST")
    parser.add_argument("--report-period", required=True, help="T.ex. 2026-Q2")
    parser.add_argument("--period-end", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--published-at",
        required=True,
        help="Rapportdatum YYYY-MM-DD. En ISO-tid med tidszon stöds också.",
    )
    parser.add_argument(
        "--effective-date",
        required=False,
        default=None,
        help="Valfritt bakåtkompatibelt fält; måste vara samma svenska dag som published_at.",
    )
    parser.add_argument(
        "--eps",
        required=False,
        type=float,
        help="Verifierad utspädd EPS för rapportperioden i bolagets rapportvaluta.",
    )
    parser.add_argument(
        "--eps-ttm",
        required=False,
        type=float,
        help="EPS TTM som ska användas direkt av strategin.",
    )
    parser.add_argument("--source", default="Manuellt registrerad bolagsrapport")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    if (args.eps is None) == (args.eps_ttm is None):
        parser.error("ange exakt ett av --eps eller --eps-ttm")

    reports = add_report(
        ticker=args.ticker,
        report_period=args.report_period,
        period_end=args.period_end,
        published_at=args.published_at,
        effective_date=args.effective_date,
        eps=args.eps,
        eps_ttm=args.eps_ttm,
        source=args.source,
        notes=args.notes,
    )
    latest = reports.loc[
        (reports["ticker"] == args.ticker)
        & (reports["report_period"] == args.report_period)
    ].iloc[-1]
    if args.eps is not None:
        print(
            f"Sparade {latest['ticker']} {latest['report_period']}: period-EPS {args.eps} -> "
            f"härledd EPS TTM {latest['eps_ttm']} från {latest['effective_date'].date()} "
            "(same-day-policy)"
        )
    else:
        print(
            f"Sparade {latest['ticker']} {latest['report_period']}: "
            f"EPS TTM {latest['eps_ttm']} från {latest['effective_date'].date()} "
            "(direkt inmatning)"
        )


if __name__ == "__main__":
    main()
