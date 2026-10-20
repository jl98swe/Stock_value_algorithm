"""Parallel source-specific EOD collection, followed by serialized reconciliation."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

from .config import ROOT
from .fetch_data import (BASE_DATA_FILE, UPDATES_FILE, RAW_PRICE_COLUMNS, _download,
                         _validate_ohlc, _updates_with_ma200)
from .intraday import (AVANZA_URL, TZ, instant, number, parse_avanza,
                       parse_avanza_open, session_bounds)
from .utils import read_json, write_json_atomic

PROVENANCE = ROOT / "data/prices/closing_sources.csv"
CUTOFFS = ROOT / ".cache/closing_recalculate.json"


def fetch_avanza_daily(instrument, now):
    """Read today's last trade and real O/H/L; do not invent a closing flag."""
    with requests.Session() as client:
        client.headers["User-Agent"] = "StockValueAlgorithm/1.0 daily prices"
        response = client.get(AVANZA_URL + instrument["avanza_id"], timeout=20)
        response.raise_for_status()
        data = response.json()
        quote = parse_avanza(data, instrument, instant())
        if not quote:
            return None
        response = client.get("https://www.avanza.se/_api/price-chart/stock/" + instrument["avanza_id"],
                              params={"timePeriod": "today"}, timeout=20)
        response.raise_for_status()
        opening = parse_avanza_open(response.json(), instrument, instant())
        if not opening or not number(quote.get("day_high")) or not number(quote.get("day_low")):
            return None
        volume = data.get("quote", {}).get("totalVolumeTraded")
        volume = float(volume) if isinstance(volume, (int, float)) and math.isfinite(volume) and volume >= 0 else None
        return {"open": opening["price"], "high": quote["day_high"], "low": quote["day_low"],
                "close": quote["latest"]["price"], "volume": volume,
                "quote_as_of": quote["latest"]["as_of"]}


def collect(source, planned, *, now=None, stocks=None, instruments=None,
            yahoo=_download, avanza=fetch_avanza_daily):
    now = instant() if now is None else now
    day = now.date().isoformat()
    bounds = session_bounds(now)
    payload = {"schema_version": 1, "source": source, "session_date": day,
               "planned_at": f"{day}T{planned}:00{now.strftime('%z')[:3]}:{now.strftime('%z')[3:]}",
               "started_at": now.isoformat(), "run_id": os.getenv("GITHUB_RUN_ID", "local"),
               "rows": [], "errors": [], "state": "not_due"}
    if not bounds or now < bounds[1]:
        payload["state"] = "not_trading_day" if not bounds else "not_due"
        payload["completed_at"] = instant().isoformat()
        return payload
    stocks = stocks if stocks is not None else read_json("docs/data/stocks.json")["stocks"]
    tickers = sorted(s["ticker"] for s in stocks if s.get("active_for_updates", True))
    payload["expected"] = len(tickers)
    if source == "Yahoo":
        started = instant().isoformat()
        try:
            frame = yahoo(tickers, start=day, end=(now.date() + timedelta(days=1)).isoformat())
            finished = instant().isoformat()
            for row in frame.to_dict("records"):
                if row.get("ticker") not in tickers or pd.Timestamp(row["date"]).date() != now.date():
                    continue
                values = {k: row[k] for k in RAW_PRICE_COLUMNS}
                values["volume"] = None if pd.isna(values["volume"]) else float(values["volume"])
                payload["rows"].append({**values, "date": day,
                    "fetch_started_at": started, "fetched_at": finished, "timing_scope": "batch",
                    "quote_as_of": None})
        except Exception as exc:
            payload["errors"].append(f"Yahoo: {type(exc).__name__}: {exc}")
    elif source == "Avanza":
        instruments = instruments if instruments is not None else read_json("config/intraday_instruments.json")
        def one(ticker):
            started = instant().isoformat()
            result = avanza(instruments[ticker], now)
            return None if not result else {**result, "ticker": ticker, "date": day,
                "fetch_started_at": started, "fetched_at": instant().isoformat(), "timing_scope": "instrument"}
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = {pool.submit(one, ticker): ticker for ticker in tickers}
            for future in as_completed(jobs):
                try:
                    row = future.result()
                    if row:
                        payload["rows"].append(row)
                except Exception as exc:
                    payload["errors"].append(f"Avanza {jobs[future]}: {type(exc).__name__}: {exc}")
    else:
        raise ValueError("Okänd kurskälla")
    valid = []
    for row in payload["rows"]:
        try:
            if not all(number(row.get(k)) for k in ("open", "high", "low", "close")):
                raise ValueError("saknad OHLC")
            _validate_ohlc(pd.DataFrame([row]))
            valid.append(row)
        except ValueError as exc:
            payload["errors"].append(f"{row['ticker']}: {exc}")
    payload["rows"] = sorted(valid, key=lambda r: r["ticker"])
    payload["available"] = len(valid)
    payload["missing"] = sorted(set(tickers) - {r["ticker"] for r in valid})
    payload["completed_at"] = instant().isoformat()
    payload["state"] = "collected" if valid else "failed"
    return payload


def apply_snapshot(payload, *, base_file=BASE_DATA_FILE, updates_file=UPDATES_FILE,
                   provenance_file=PROVENANCE, now=None):
    """Apply on the latest branch tip, regardless of producer completion order.

    Existing rows without provenance are treated as Yahoo. Yahoo always wins
    over Avanza; an older response from the same source cannot replace a newer
    response. Avanza still records comparisons when it has nothing to fill.
    """
    source, day = payload["source"], payload["session_date"]
    if source not in {"Yahoo", "Avanza"}:
        raise ValueError("Okänd kurskälla")
    received = instant() if now is None else now
    bounds = session_bounds(instant(payload["started_at"]))
    if not bounds or instant(payload["started_at"]) < bounds[1] or day != received.date().isoformat():
        raise ValueError("Snapshot gäller inte dagens avslutade handelssession")
    base = pd.read_parquet(base_file)
    base["date"] = pd.to_datetime(base.date)
    updates = pd.read_csv(updates_file) if Path(updates_file).exists() else pd.DataFrame(columns=RAW_PRICE_COLUMNS)
    updates["date"] = pd.to_datetime(updates.date)
    provenance = pd.read_csv(provenance_file).to_dict("records") if Path(provenance_file).exists() else []
    by_key = {(str(r["ticker"]), str(r["date"])[:10]): r for r in provenance}
    combined = pd.concat([base, updates], ignore_index=True).drop_duplicates(["ticker", "date"], keep="last")
    existing = {(str(r.ticker), pd.Timestamp(r.date).date().isoformat()): r for r in combined.itertuples()}
    report = {k: v for k, v in payload.items() if k != "rows"}
    report.update(applied=0, kept=0, differences=[], observed=payload["rows"])
    cutoffs = {}
    for row in payload["rows"]:
        if row["date"] != day:
            raise ValueError("Fel datum i snapshot")
        if not all(number(row.get(k)) for k in ("open", "high", "low", "close")):
            raise ValueError("Ofullständig OHLC")
        _validate_ohlc(pd.DataFrame([row]))
        key = (row["ticker"], day)
        old = existing.get(key)
        previous = by_key.get(key, {"source": "Yahoo", "fetched_at": ""})
        if old is not None:
            report["differences"].append({"ticker": row["ticker"], "incoming_source": source,
                "existing_source": previous["source"], "incoming_close": row["close"],
                "existing_close": float(old.close), "delta": float(row["close"] - old.close)})
        keep = old is not None and ((source == "Avanza" and previous["source"] == "Yahoo") or
            (source == previous["source"] and previous.get("fetched_at", "") and
             instant(previous["fetched_at"]) > instant(row["fetched_at"])))
        if keep:
            report["kept"] += 1
            continue
        # The frozen base is never rewritten by a live-source collection.
        base_dates = base.loc[base.ticker.eq(row["ticker"]), "date"]
        if len(base_dates) and pd.Timestamp(day) <= base_dates.max():
            raise ValueError("Snapshot får inte ändra fryst prisbas")
        updates = updates.loc[~(updates.ticker.eq(row["ticker"]) & updates.date.eq(pd.Timestamp(day)))]
        updates = pd.concat([updates, pd.DataFrame([{**{k: row.get(k) for k in RAW_PRICE_COLUMNS},
                                                   "date": pd.Timestamp(day)}])], ignore_index=True)
        by_key[key] = {"ticker": row["ticker"], "date": day, "source": source, "fetched_at": row["fetched_at"]}
        if old is None or any(float(getattr(old, k)) != float(row[k]) for k in ("open", "high", "low", "close")):
            cutoffs[row["ticker"]] = day
        report["applied"] += 1
    if report["applied"]:
        _, normalized = _updates_with_ma200(base, updates)
        normalized.to_csv(updates_file, index=False, date_format="%Y-%m-%d")
    Path(provenance_file).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(by_key.values(), columns=["ticker", "date", "source", "fetched_at"]).sort_values(["date", "ticker"]).to_csv(provenance_file, index=False)
    report["recalculate_from"] = cutoffs
    report["applied_at"] = received.isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["collect", "apply", "build"])
    parser.add_argument("--source", choices=["Yahoo", "Avanza"], default="Yahoo")
    parser.add_argument("--planned", default="17:30")
    parser.add_argument("--file", type=Path, default=ROOT / ".cache/closing_snapshot.json")
    parser.add_argument("--defer-score-history", action="store_true")
    args = parser.parse_args()
    if args.mode == "collect":
        result = collect(args.source, args.planned)
        write_json_atomic(args.file, result)
        print(json.dumps({k:v for k,v in result.items() if k != "rows"}, ensure_ascii=False))
        if output := os.getenv("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as f:
                f.write(f"ready={'true' if result.get('rows') else 'false'}\n")
        if result["state"] == "failed":
            raise RuntimeError("Källan gav ingen giltig dagsdata")
    elif args.mode == "apply":
        payload = json.loads(args.file.read_text())
        result = apply_snapshot(payload)
        write_json_atomic(CUTOFFS, result["recalculate_from"])
        audit = ROOT / "data/prices/closing_audit" / payload["session_date"] / f"{payload['source']}-{payload['run_id']}.json"
        write_json_atomic(audit, result)
        print(json.dumps({k:v for k,v in result.items() if k not in {"observed", "differences"}}, ensure_ascii=False))
    else:
        command = [sys.executable, "-m", "src.pipeline", "--skip-fetch"]
        command.append("--defer-score-history" if args.defer_score_history else "--skip-dividends")
        for ticker, day in read_json(CUTOFFS, {}).items():
            command.extend(["--recalculate-score-from", f"{ticker}={day}"])
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
