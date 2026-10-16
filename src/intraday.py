"""Shared, disposable display quotes. Never input to valuation or price history.

Avanza is queried first for every instrument. Nasdaq's public MiFID post-trade
files fill missing or stale quotes and missing opening prices. Instrument
identity, currency and the current session are checked before using quotes.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import requests

from .config import ROOT
from .utils import read_json, write_json_atomic

TZ = ZoneInfo("Europe/Stockholm")
CACHE_BRANCH = "intraday-cache"
REPOSITORY = "jl98swe/Stock_value_algorithm"
CACHE_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/{CACHE_BRANCH}/intraday.json"
NASDAQ_URL = "https://tradereports.nasdaq.com/api/regulatory"
AVANZA_URL = "https://www.avanza.se/_api/market-guide/stock/"
SLOTS = ("09:00", "13:00", "17:00", "17:30")


def instant(value=None) -> datetime:
    if value is None:
        return datetime.now(TZ)
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Kurstid måste innehålla tidszon")
    return result.astimezone(TZ)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def session_bounds(now: datetime):
    calendar = xcals.get_calendar("XSTO")
    day = pd.Timestamp(now.date())
    if not calendar.is_session(day):
        return None
    return (calendar.session_open(day).to_pydatetime().astimezone(TZ),
            calendar.session_close(day).to_pydatetime().astimezone(TZ))


def read_cache(client=requests) -> dict:
    response = client.get(CACHE_URL, params={"t": int(datetime.now().timestamp())}, timeout=25)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    result = response.json()
    if result.get("schema_version") != 1:
        raise ValueError("Okänt schema i intradagscache")
    return result


def prune(cache: dict, stocks: list[dict], now: datetime) -> dict:
    """Remove each quote only after its matching EOD has actually been published."""
    day = now.date().isoformat()
    output = copy.deepcopy(cache) if cache.get("session_date") == day else {}
    output.update(schema_version=1, session_date=day, generated_at=now.isoformat(),
                  expires_at=(now.replace(hour=0, minute=0, second=0, microsecond=0)
                              + timedelta(days=1)).isoformat(), schedule=list(SLOTS))
    active = {s["ticker"]: s for s in stocks if s.get("active_for_updates", True)}
    output["stocks"] = {
        ticker: row for ticker, row in output.get("stocks", {}).items()
        if ticker in active and str(active[ticker].get("latest_date", "")) < day
    }
    expected = sum(str(stock.get("latest_date", "")) < day for stock in active.values())
    output["coverage"] = {"available": sum(bool(row.get("latest")) for row in output["stocks"].values()),
                          "expected": expected}
    output["collection_state"] = "completed" if not expected else "pending"
    output.pop("errors", None)
    return output


def choose_files(names: list[str], now: datetime, need_open: bool) -> list[str]:
    """Only process files already 15 minutes old, including half-day auctions."""
    bounds = session_bounds(now)
    cutoff = min(now - timedelta(minutes=15), bounds[1]) if bounds else now - timedelta(minutes=15)
    dated = []
    for name in names:
        match = re.fullmatch(r"NordicEquity-posttrade-(\d{4}-\d{2}-\d{2}T\d{4})", name)
        if not match:
            continue  # No previous-day files or potentially enormous daily dumps.
        at = datetime.strptime(match[1], "%Y-%m-%dT%H%M").replace(tzinfo=TZ)
        if at.date() == now.date() and at <= cutoff:
            dated.append((at, name))
    dated.sort()
    selected = {name for _, name in dated[-5:]}
    if need_open:
        if bounds:
            opening = bounds[0]
            selected.update(name for at, name in dated
                            if opening <= at < opening + timedelta(minutes=5))
    return sorted(selected)


def parse_trades(text: str, instruments: dict, now: datetime) -> dict:
    """Build latest and first regular on-venue trades; retain their actual times."""
    by_isin = {row["isin"]: ticker for ticker, row in instruments.items()}
    lines = text.lstrip("\ufeff").splitlines()
    if lines and "sep=" in lines[0]:
        lines = lines[1:]
        if not any(line.strip() for line in lines):
            return {}  # Nasdaq publishes separator-only files for empty minutes.
    rows = csv.DictReader(lines, delimiter=";")
    required = {"Trading date and time", "Instrument identification code", "Price",
                "Price currency", "Venue of execution", "Trading system", "Flags"}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError("Nasdaq-filen saknar förväntade avslutskolumner")
    bounds = session_bounds(now)
    if not bounds:
        return {}
    opening, closing = bounds
    result = {}
    for row in rows:
        ticker = by_isin.get(row["Instrument identification code"])
        if not ticker or row["Price currency"] != instruments[ticker]["currency"]:
            continue
        if row["Venue of execution"] not in {"XSTO", "FNSE", "SSME"}:
            continue
        if row["Trading system"] not in {"CLOB", "PATS"}:
            continue  # Do not turn off-book negotiated trades into display quotes.
        if any(flag in row["Flags"].split(",") for flag in ("CANC", "AMND")):
            continue
        price = number(row["Price"])
        try:
            at = instant(row["Trading date and time"])
        except ValueError:
            continue
        if price is None or not opening <= at <= min(now, closing):
            continue
        observation = {"price": price, "as_of": at.isoformat(), "source": "Nasdaq",
                       "delay_minutes": 15, "currency": row["Price currency"]}
        item = result.setdefault(ticker, {})
        if not item.get("latest") or at > instant(item["latest"]["as_of"]):
            item["latest"] = observation
        # A first trade at 13:00 is not the session opening trade. Avanza's
        # complete daily chart supplies opens absent from the opening window.
        if at < opening + timedelta(minutes=5):
            if not item.get("opening") or at < instant(item["opening"]["as_of"]):
                item["opening"] = observation
    return result


def merge_nasdaq(target: dict, incoming: dict) -> None:
    for ticker, data in incoming.items():
        item = target.setdefault(ticker, {})
        for field, quote in data.items():
            previous = item.get(field)
            if (not previous or (field == "opening" and previous.get("source") != "Nasdaq") or
                (instant(quote["as_of"]) > instant(previous["as_of"]) if field == "latest"
                 else instant(quote["as_of"]) < instant(previous["as_of"]))):
                item[field] = quote


def fetch_nasdaq(client, instruments: dict, now: datetime, need_open: bool) -> tuple[dict, list[str]]:
    response = client.get(NASDAQ_URL + "/trade-reports", params={
        "type": "POST_TRADE", "assetClass": "EQUITY"}, timeout=30)
    response.raise_for_status()
    names = choose_files(response.json()["reports"], now, need_open)
    result, errors = {}, []
    opening_ok = True
    # Sequential downloads avoid imposing large bursts on the public service.
    for name in names:
        try:
            response = client.get(NASDAQ_URL + "/trade-report/download", params={
                "type": "POST_TRADE", "assetClass": "EQUITY", "fileName": name}, timeout=45)
            response.raise_for_status()
            merge_nasdaq(result, parse_trades(response.content.decode("utf-8-sig"), instruments, now))
        except (requests.RequestException, ValueError) as error:
            errors.append(f"Nasdaq {name}: {type(error).__name__}")
            if name.endswith(tuple(f"T090{i}" for i in range(5))):
                opening_ok = False
    # A failed early file could contain the real opening trade.
    if not opening_ok:
        for item in result.values():
            item.pop("opening", None)
    return result, errors


def parse_avanza(data: dict, instrument: dict, now: datetime) -> dict:
    listing, quote = data.get("listing", {}), data.get("quote", {})
    if data.get("isin") != instrument["isin"] or listing.get("currency") != instrument["currency"]:
        raise ValueError("Avanza: fel ISIN eller valuta")
    if listing.get("tickerSymbol") != instrument.get("avanza_symbol"):
        raise ValueError("Avanza: fel aktieslag")
    bounds = session_bounds(now)
    if not bounds or not number(quote.get("last")) or not quote.get("timeOfLast"):
        return {}
    at = datetime.fromtimestamp(quote["timeOfLast"] / 1000, TZ)
    if not bounds[0] <= at <= min(now, bounds[1]):
        return {}  # Yesterday's last trade must never look like today's quote.
    previous = number(data.get("historicalClosingPrices", {}).get("oneDay"))
    return {"latest": {"price": float(quote["last"]), "as_of": at.isoformat(),
                       "source": "Avanza", "currency": instrument["currency"],
                       "delayed": not bool(quote.get("isRealTime"))},
            "day_high": number(quote.get("highest")), "day_low": number(quote.get("lowest")),
            "previous_close": previous}


def fetch_avanza(instrument: dict, now: datetime, need_open: bool) -> dict:
    if not instrument.get("avanza_id"):
        return {}
    with requests.Session() as client:
        client.headers["User-Agent"] = "StockValueAlgorithm/1.0 intraday quotes"
        response = client.get(AVANZA_URL + instrument["avanza_id"], timeout=20)
        response.raise_for_status()
        # The universe is fetched over several minutes. Validate against the
        # response time, not the start of the whole collection. Keep --as-of
        # on its requested session when inspecting an older day.
        received = datetime.now(TZ)
        observed = max(now, received) if received.date() == now.date() else now
        result = parse_avanza(response.json(), instrument, observed)
        if need_open and result:
            response = client.get("https://www.avanza.se/_api/price-chart/stock/" +
                                  instrument["avanza_id"], params={"timePeriod": "today"}, timeout=20)
            response.raise_for_status()
            received = datetime.now(TZ)
            observed = max(now, received) if received.date() == now.date() else now
            opening = parse_avanza_open(response.json(), instrument, observed)
            if opening:
                result["opening"] = opening
        return result


def parse_avanza_open(data: dict, instrument: dict, now: datetime):
    bounds = session_bounds(now)
    candidates = []
    for row in data.get("ohlc", []):
        at = datetime.fromtimestamp(row["timestamp"] / 1000, TZ)
        if bounds and bounds[0] <= at <= min(now, bounds[1]) and number(row.get("open")):
            candidates.append((at, float(row["open"])))
    if not candidates:
        return None
    at, price = min(candidates)
    return {"price": price, "as_of": at.isoformat(), "source": "Avanza",
            "currency": instrument["currency"], "delayed": True}


def collect(cache: dict, stocks: list[dict], instruments: dict, now: datetime,
            client=requests, primary=fetch_avanza) -> dict:
    output = prune(cache, stocks, now)
    bounds = session_bounds(now)
    if not bounds:
        output["collection_state"] = "not_trading_day"
    if not bounds or now < bounds[0] or now > bounds[1] + timedelta(hours=2):
        return output
    day = now.date().isoformat()
    eligible = {s["ticker"]: s for s in stocks if s.get("active_for_updates", True)
                and str(s.get("latest_date", "")) < day}
    if not eligible:
        return output
    instruments = {t: row for t, row in instruments.items() if t in eligible and row.get("isin")}
    rows = output["stocks"]
    errors = []
    stale_before = min(now - timedelta(minutes=30), bounds[1] - timedelta(minutes=15))
    fresh_primary = set()
    failed_primary = set()
    # Always refresh the full universe from the primary source at each due slot.
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(primary, instruments[t], now, not rows.get(t, {}).get("opening")
                            or rows[t]["opening"].get("source") != "Avanza"): t for t in instruments}
        for future in as_completed(jobs):
            ticker = jobs[future]
            try:
                data = future.result()
                item = rows.setdefault(ticker, {})
                if data.get("opening") and (not item.get("opening") or item["opening"].get("source") != "Avanza"):
                    item["opening"] = data["opening"]
                quote = data.get("latest")
                if quote and instant(quote["as_of"]) >= stale_before:
                    fresh_primary.add(ticker)
                if not quote:
                    failed_primary.add(ticker)
                if quote and (not item.get("latest") or
                              (ticker in fresh_primary and item["latest"].get("source") != "Avanza") or
                              instant(quote["as_of"]) >= instant(item["latest"]["as_of"])):
                    item["latest"] = quote
                for field in ("day_high", "day_low"):
                    if data.get(field) is not None:
                        item[field] = data[field]
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                failed_primary.add(ticker)
                errors.append(f"Avanza {ticker}: {type(error).__name__}")
    needs = {t: instruments[t] for t in instruments if t in failed_primary or
             not rows.get(t, {}).get("opening") or not rows.get(t, {}).get("latest") or
             instant(rows[t]["latest"]["as_of"]) < stale_before}
    if needs:
        try:
            incoming, secondary_errors = fetch_nasdaq(client, needs, now,
                                           any(not rows.get(t, {}).get("opening") for t in needs))
            errors.extend(secondary_errors)
            for ticker, data in incoming.items():
                if ticker in fresh_primary:
                    data.pop("latest", None)
                if rows.get(ticker, {}).get("opening"):
                    data.pop("opening", None)
            merge_nasdaq(rows, incoming)
        except (requests.RequestException, ValueError, KeyError) as error:
            errors.append(f"Nasdaq: {type(error).__name__}")
    for ticker in eligible:
        item = rows.setdefault(ticker, {})
        latest = item.get("latest")
        previous = number(eligible[ticker].get("latest_close"))
        # Cached quote can be older than a fallback opening chart; do not imply
        # high/low are available from our sparse Nasdaq sample.
        if latest and previous:
            latest["change_pct"] = round((latest["price"] / previous - 1) * 100, 4)
        item["status"] = "available" if latest else "awaiting_trade"
    output["errors"] = errors
    output["coverage"] = {"available": sum(bool(x.get("latest")) for x in rows.values()),
                          "expected": len(eligible)}
    fresh = any(row.get("latest") and instant(row["latest"]["as_of"]) >= stale_before for row in rows.values())
    output["collection_state"] = "available" if fresh else "stale"
    return output


def publish(payload: dict) -> None:
    """Replace the dedicated cache ref with one parentless snapshot, never main.

    The branch intentionally has no growing history. Force-with-lease prevents
    an older concurrent producer from overwriting a newer snapshot. Workflows
    additionally serialize collection and EOD cleanup.
    """
    if os.getenv("GITHUB_REF_NAME", "main") != "main":
        raise ValueError("Intradagscachen får bara publiceras från main")
    branch = CACHE_BRANCH
    remote = f"refs/heads/{branch}"
    listed = subprocess.check_output(["git", "ls-remote", "origin", remote], cwd=ROOT, text=True).strip()
    previous = listed.split()[0] if listed else ""
    with tempfile.TemporaryDirectory(prefix="intraday-index-") as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"),
                   GIT_AUTHOR_NAME="github-actions[bot]", GIT_COMMITTER_NAME="github-actions[bot]",
                   GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
                   GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
        def git(*args, content=None):
            return subprocess.check_output(["git", *args], cwd=ROOT, env=env, input=content, text=True).strip()
        git("read-tree", "--empty")
        blob = git("hash-object", "-w", "--stdin", content=json.dumps(payload, ensure_ascii=False, allow_nan=False))
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},intraday.json")
        tree = git("write-tree")
        commit = git("commit-tree", tree, "-m", "cache: replace temporary intraday quotes")
        git("push", f"--force-with-lease={remote}:{previous}", "origin", f"{commit}:{remote}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--as-of")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/intraday.json")
    args = parser.parse_args()
    now = instant(args.as_of)
    stocks = read_json("docs/data/stocks.json")["stocks"]
    # A failed cache read must not silently replace good shared data with empty.
    cache = read_cache()
    if args.cleanup:
        output = prune(cache, stocks, now)
    else:
        output = collect(cache, stocks, read_json("config/intraday_instruments.json"), now)
    write_json_atomic(args.output, output)
    print(json.dumps({"session_date": output["session_date"], "coverage": output.get("coverage"),
                      "cached_stocks": len(output["stocks"]), "errors": output.get("errors", [])}, ensure_ascii=False))
    if args.publish:
        publish(output)
    if output.get("coverage", {}).get("expected", 0) and not output["coverage"]["available"]:
        bounds = session_bounds(now)
        if bounds and now >= bounds[0] + timedelta(minutes=20):
            raise RuntimeError("Ingen aktuell kurs kunde hämtas; kontrollera källornas fel i körloggen")


if __name__ == "__main__":
    main()
