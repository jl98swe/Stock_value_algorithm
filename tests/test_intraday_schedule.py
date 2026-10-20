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


def test_final_slot_is_due_at_1600_and_delayed_collection_remains_allowed():
    midday = cache("2026-10-16T13:08:00+02:00")
    assert not decision(at("2026-10-16T15:59:00+02:00"), midday)[0]
    assert decision(at("2026-10-16T16:00:00+02:00"), midday)[0]
    assert decision(at("2026-10-16T19:35:00+02:00"), midday)[0]
    assert decision(at("2026-10-16T23:59:00+02:00"), {})[0]
    assert not decision(at("2026-10-16T19:35:00+02:00"),
                        cache("2026-10-16T16:08:00+02:00"))[0]


def test_workflow_and_cache_advertise_the_same_intraday_times():
    from pathlib import Path
    import yaml
    from src.intraday import SLOTS as cache_slots
    from src.intraday_schedule import SLOTS
    workflow = yaml.safe_load((Path(__file__).parents[1] /
                               ".github/workflows/intraday_quotes.yml").read_text())
    trigger = workflow.get("on", workflow.get(True))
    assert trigger["schedule"][0] == {"cron": "0 13,16 * * 1-5",
                                      "timezone": "Europe/Stockholm"}
    assert SLOTS == cache_slots == ("09:20", "13:00", "16:00")
