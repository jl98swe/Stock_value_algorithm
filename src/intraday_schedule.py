"""Cheap, dependency-free catch-up check before installing collection packages.

GitHub cron is best effort. Both the ordinary schedule and the independent UTC
retry schedule use this check against the shared cache. Delayed jobs collapse
to one collection for the latest due slot, using Stockholm local time and DST.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
CACHE_URL = "https://raw.githubusercontent.com/jl98swe/Stock_value_algorithm/intraday-cache/intraday.json"
SLOTS = ("09:20", "13:00", "17:00")


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(TZ) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def decision(now: datetime, cache: dict) -> tuple[bool, str]:
    cache = cache if isinstance(cache, dict) else {}
    now = now.astimezone(TZ)
    if now.weekday() >= 5:
        return False, "Helg"
    if now.hour >= 18:
        return False, "Kvällens dagskurser hanteras av Yahoo och Avanza separat"
    slots = [now.replace(hour=int(s[:2]), minute=int(s[3:]), second=0, microsecond=0) for s in SLOTS]
    due = [slot for slot in slots if slot <= now]
    if not due:
        return False, "Inväntar öppningskurs från 09.20"
    slot = due[-1]
    day = now.date().isoformat()
    generated = timestamp(cache.get("generated_at"))
    expires = timestamp(cache.get("expires_at"))
    valid = (cache.get("schema_version") == 1 and cache.get("session_date") == day and
             generated is not None and generated <= now + timedelta(minutes=1) and
             expires is not None and expires > now)
    if valid:
        state = cache.get("collection_state")
        if state in {"completed", "not_trading_day"}:
            return False, "Dagens stängningskurser klara eller ingen handelsdag"
        has_quotes = any(
            timestamp(row.get("latest", {}).get("as_of")) is not None and
            timestamp(row["latest"]["as_of"]).date() == now.date()
            for row in cache.get("stocks", {}).values()
        )
        if generated >= slot and has_quotes and state in {None, "available"}:
            return False, f"Tiden {slot:%H.%M} är redan hämtad"
    return True, f"Saknad eller misslyckad hämtning för {slot:%H.%M}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    if not args.scheduled:
        run, reason = True, "Manuell körning, kodpublicering eller rensning"
    else:
        now = datetime.now(TZ)
        cache = {}
        # Only network work in this cheap gate: one small public JSON file.
        # A read failure must not cause a missed collection; the collector
        # still protects the current cache from being overwritten on errors.
        try:
            request = urllib.request.Request(f"{CACHE_URL}?t={int(now.timestamp())}",
                                             headers={"User-Agent": "StockValueAlgorithm-schedule"})
            with urllib.request.urlopen(request, timeout=15) as response:
                cache = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        run, reason = decision(now, cache)
    print(reason)
    if output := os.getenv("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as target:
            target.write(f"run={'true' if run else 'false'}\n")


if __name__ == "__main__":
    main()
