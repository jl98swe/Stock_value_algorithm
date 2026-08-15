from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ROOT
from .utils import write_json_atomic

DASHBOARD_FILE = ROOT / "docs" / "data" / "dashboard.json"
DEFAULT_START_DATE = "2024-01-01"


def _day(value: object) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _filter_dated_rows(rows: object, start_date: str, *date_fields: str) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        return []

    output: list[dict[str, object]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        date_value = ""
        for field in date_fields:
            date_value = _day(item.get(field))
            if date_value:
                break
        if date_value and date_value >= start_date:
            output.append(item)
    return output


def limit_dashboard(
    path: Path = DASHBOARD_FILE,
    *,
    start_date: str = DEFAULT_START_DATE,
) -> dict[str, object]:
    target = path if path.is_absolute() else ROOT / path
    if not target.exists() or target.stat().st_size == 0:
        raise FileNotFoundError(target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    stocks = payload.get("stocks")
    if not isinstance(stocks, dict):
        raise ValueError("dashboard.json saknar stocks-objekt")

    for ticker, stock in stocks.items():
        if not isinstance(stock, dict):
            raise ValueError(f"Ogiltigt dashboard-objekt för {ticker}")

        stock["candles"] = _filter_dated_rows(stock.get("candles"), start_date, "date")
        stock["scores"] = _filter_dated_rows(stock.get("scores"), start_date, "date")
        stock["signals"] = _filter_dated_rows(stock.get("signals"), start_date, "date", "signal_date")
        # Visa bara avslut där även inträdet ligger inom dashboardens tidsfönster.
        stock["closed_trades"] = _filter_dated_rows(
            stock.get("closed_trades"), start_date, "entry_date"
        )

        if not stock["candles"]:
            raise ValueError(f"{ticker} saknar prisdata från {start_date} och framåt")

        for field in ("candles", "scores", "signals"):
            for row in stock[field]:
                day = _day(row.get("date") or row.get("signal_date"))
                if day and day < start_date:
                    raise ValueError(f"{ticker}: {field} innehåller datum före {start_date}: {day}")
        for row in stock["closed_trades"]:
            day = _day(row.get("entry_date"))
            if day and day < start_date:
                raise ValueError(f"{ticker}: closed_trades innehåller inträde före {start_date}: {day}")

    meta = payload.setdefault("meta", {})
    if not isinstance(meta, dict):
        raise ValueError("dashboard.json meta måste vara ett objekt")
    meta["frontend_start_date"] = start_date
    meta["frontend_scope_note"] = (
        "Pris, score, signaler och visade avslut begränsas i dashboarden. "
        "Underliggande historik och beräkningarnas uppvärmningsdata behålls oförändrade."
    )

    write_json_atomic(target, payload)
    print(
        f"Dashboard begränsad till {start_date} och framåt för {len(stocks)} tickers. "
        "events.json/nyhetsflödet ändrades inte."
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Begränsa dashboardens visade marknads- och strategihistorik utan att kapa rådata."
    )
    parser.add_argument("--path", type=Path, default=DASHBOARD_FILE)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    args = parser.parse_args()
    limit_dashboard(args.path, start_date=args.start_date)


if __name__ == "__main__":
    main()
