from datetime import datetime

import pytest

from src.intraday_schedule import decision


def at(value):
    return datetime.fromisoformat(value)


def cache(generated="2026-10-16T09:23:00+02:00", state="available"):
    return {"schema_version": 1, "session_date": "2026-10-16",
            "generated_at": generated, "expires_at": "2026-10-17T00:00:00+02:00",
            "collection_state": state,
            "stocks": {"EXAMPLE.ST": {"latest": {"as_of": "2026-10-16T09:05:00+02:00"}}}}


@pytest.mark.parametrize("now,expected", [
    ("2026-10-16T07:19:00+00:00", False),
    ("2026-10-16T07:20:00+00:00", True),
    ("2026-01-16T08:19:00+00:00", False),
    ("2026-01-16T08:20:00+00:00", True),
    ("2026-10-17T13:00:00+02:00", False),
])
def test_missing_cache_obeys_stockholm_opening_dst_and_weekend(now, expected):
    assert decision(at(now), {})[0] is expected


def test_delayed_duplicate_is_skipped_but_next_slot_is_collected():
    assert not decision(at("2026-10-16T12:55:00+02:00"), cache())[0]
    assert decision(at("2026-10-16T13:07:00+02:00"), cache())[0]
    assert not decision(at("2026-10-16T13:22:00+02:00"),
                        cache("2026-10-16T13:08:00+02:00"))[0]


def test_failed_stale_or_invalid_snapshot_cannot_suppress_retry():
    now = at("2026-10-16T09:30:00+02:00")
    assert decision(now, cache(state="stale"))[0]
    assert decision(now, cache("2026-10-16T14:00:00+02:00"))[0]
    assert decision(now, {**cache(), "session_date": "2026-10-15"})[0]
    assert decision(now, {**cache(), "stocks": {}})[0]
    assert decision(now, [])[0]


@pytest.mark.parametrize("state", ["completed", "not_trading_day"])
def test_completed_day_is_not_repopulated_by_later_retry(state):
    assert not decision(at("2026-10-16T18:55:00+02:00"),
                        {**cache(state=state), "stocks": {}})[0]
