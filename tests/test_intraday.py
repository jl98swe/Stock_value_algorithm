"""Synthetic examples: delayed display quotes cannot become daily prices."""
import pytest

from src import intraday as q

NOW = q.instant("2026-10-15T13:00:00+02:00")
INSTRUMENTS = {"EXAMPLE-A.ST": {"isin": "SE0000000001", "currency": "SEK",
                                "avanza_id": "123", "avanza_symbol": "EXAMPLE A"}}
STOCKS = [{"ticker": "EXAMPLE-A.ST", "latest_date": "2026-10-14", "latest_close": 100,
           "active_for_updates": True}]
HEADER = '"sep=;"\nTrading date and time;Instrument identification code;Price;Missing Price;Price currency;Price notation;Quantity;Venue of execution;Trading system;Publication date and time;Venue of publication;Transaction identification code;Flags\n'


def trade(at, price, *, currency="SEK", venue="XSTO", system="CLOB", flags="ALGO"):
    return f"2026-10-15T{at}Z;SE0000000001;{price};;{currency};MONE;10;{venue};{system};;;1;{flags}\n"


def quote(at="2026-10-15T12:44:00+02:00", price=102, source="Nasdaq"):
    return {"as_of": at, "price": price, "source": source, "currency": "SEK"}


def test_nasdaq_filters_currency_venue_offbook_future_and_cancellations():
    data = HEADER + trade("07:00:30", 100) + trade("10:40:00", 101)
    data += trade("10:41:00", 900, currency="EUR") + trade("10:42:00", 900, venue="XHEL")
    data += trade("10:43:00", 900, system="OFFB") + trade("10:44:00", 900, flags="CANC")
    data += trade("12:00:00", 900) + trade("10:45:00", "nan")
    result = q.parse_trades(data, INSTRUMENTS, NOW)["EXAMPLE-A.ST"]
    assert result["opening"]["price"] == 100
    assert result["latest"]["price"] == 101
    assert result["latest"]["as_of"] == "2026-10-15T12:40:00+02:00"


def test_partial_midday_file_does_not_invent_opening_or_daily_high_low():
    assert q.parse_trades('"sep=;"\r\n', INSTRUMENTS, NOW) == {}
    result = q.parse_trades(HEADER + trade("10:40:00", 101), INSTRUMENTS, NOW)
    assert "opening" not in result["EXAMPLE-A.ST"]
    assert "day_high" not in result["EXAMPLE-A.ST"]
    with pytest.raises(ValueError):
        q.parse_trades("<html>Service unavailable</html>", INSTRUMENTS, NOW)


def test_actual_download_path_parses_files_and_rejects_partial_open(monkeypatch):
    class Reply:
        def __init__(self, text="", failed=False):
            self.content = text.encode()
            self.failed = failed
        def raise_for_status(self):
            if self.failed:
                raise q.requests.HTTPError("synthetic failure")
        def json(self):
            return {"reports": ["NordicEquity-posttrade-2026-10-15T0900",
                                 "NordicEquity-posttrade-2026-10-15T0901",
                                 "NordicEquity-posttrade-2026-10-15T1244"]}
    class Client:
        def get(self, url, params, **kwargs):
            name = params.get("fileName", "")
            if name.endswith("T0900"):
                return Reply(failed=True)
            if name.endswith("T0901"):
                return Reply(HEADER + trade("07:01:00", 100))
            return Reply(HEADER + trade("10:44:00", 102)) if name else Reply()
    result, errors = q.fetch_nasdaq(Client(), INSTRUMENTS, NOW, True)
    assert result["EXAMPLE-A.ST"]["latest"]["price"] == 102
    assert "opening" not in result["EXAMPLE-A.ST"]
    assert len(errors) == 1


def test_files_use_local_clock_and_only_available_delay_window():
    names = [f"NordicEquity-posttrade-2026-10-15T{clock}" for clock in
             ["0900", "0901", "0902", "1241", "1242", "1243", "1244", "1245", "1246", "1300"]]
    names += ["NordicEquity-posttrade-2026-10-14T1245", "NordicEquity-posttrade-2026-10-15"]
    selected = q.choose_files(names, NOW, True)
    assert len(selected) == 8
    assert names[0] in selected
    assert names[7] in selected
    assert names[8] not in selected and names[-1] not in selected


def test_calendar_handles_holiday_half_day_and_winter_time():
    assert q.session_bounds(q.instant("2026-04-06T12:00:00+02:00")) is None
    assert q.session_bounds(q.instant("2026-04-02T12:00:00+02:00"))[1].hour == 13
    opening, closing = q.session_bounds(q.instant("2026-01-07T12:00:00+01:00"))
    assert opening.hour == 9 and closing.hour == 17
    assert closing.utcoffset().total_seconds() == 3600


def test_after_close_downloads_include_auction_instead_of_empty_after_hours():
    names = [f"NordicEquity-posttrade-2026-10-15T{clock}" for clock in
             ["1727", "1728", "1729", "1730", "1731", "1732", "1733", "1734", "1735"]]
    selected = q.choose_files(names, q.instant("2026-10-15T17:50:00+02:00"), False)
    assert names[2] in selected
    assert names[3] in selected
    assert names[4] not in selected


def test_cleanup_is_per_stock_and_only_after_published_matching_close():
    cache = {"session_date": "2026-10-15", "stocks": {"EXAMPLE-A.ST": {"latest": quote()},
                                                        "OTHER.ST": {"latest": quote()}}}
    stocks = STOCKS + [{"ticker": "OTHER.ST", "latest_date": "2026-10-15"}]
    cache["coverage"] = {"available": 118, "expected": 118}
    cache["errors"] = ["old error"]
    partial = q.prune(cache, stocks, NOW)
    assert set(partial["stocks"]) == {"EXAMPLE-A.ST"}
    assert partial["coverage"] == {"available": 1, "expected": 1}
    assert "errors" not in partial
    completed = q.prune(cache, [{**STOCKS[0], "latest_date": "2026-10-15"}], NOW)
    assert completed["coverage"] == {"available": 0, "expected": 0}
    assert completed["collection_state"] == "completed"
    assert q.prune(cache, STOCKS, q.instant("2026-10-16T08:00:00+02:00"))["stocks"] == {}
    assert "OTHER.ST" in cache["stocks"]  # Input never mutated.


def avanza(at="2026-10-15T12:44:00+02:00"):
    return {"isin": "SE0000000001", "listing": {"currency": "SEK", "tickerSymbol": "EXAMPLE A"},
            "quote": {"last": 102, "timeOfLast": q.instant(at).timestamp() * 1000, "isRealTime": False}}


def test_avanza_checks_identity_currency_and_session_timestamp():
    instrument = INSTRUMENTS["EXAMPLE-A.ST"]
    assert q.parse_avanza(avanza(), instrument, NOW)["latest"]["price"] == 102
    assert q.parse_avanza(avanza("2026-10-14T17:29:00+02:00"), instrument, NOW) == {}
    assert q.parse_avanza(avanza("2026-10-15T14:00:00+02:00"), instrument, NOW) == {}
    wrong = avanza()
    wrong["listing"]["tickerSymbol"] = "EXAMPLE B"
    with pytest.raises(ValueError):
        q.parse_avanza(wrong, instrument, NOW)
    wrong = avanza()
    wrong["isin"] = "OTHER"
    with pytest.raises(ValueError):
        q.parse_avanza(wrong, instrument, NOW)


def test_avanza_accepts_trade_after_batch_start_but_not_after_response(monkeypatch):
    class Clock(q.datetime):
        @classmethod
        def now(cls, tz=None):
            return q.instant("2026-10-15T13:03:00+02:00")
    class Reply:
        def raise_for_status(self):
            pass
        def json(self):
            return avanza("2026-10-15T13:02:00+02:00")
    class Client:
        headers = {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, *args, **kwargs):
            return Reply()
    monkeypatch.setattr(q, "datetime", Clock)
    monkeypatch.setattr(q.requests, "Session", Client)
    result = q.fetch_avanza(INSTRUMENTS["EXAMPLE-A.ST"], NOW, False)
    assert result["latest"]["as_of"] == "2026-10-15T13:02:00+02:00"
    assert q.parse_avanza(avanza("2026-10-15T13:04:00+02:00"),
                          INSTRUMENTS["EXAMPLE-A.ST"], Clock.now()) == {}
    # A historical --as-of must still reject a quote from another session.
    assert q.fetch_avanza(INSTRUMENTS["EXAMPLE-A.ST"],
                          q.instant("2026-10-14T13:00:00+02:00"), False) == {}


def test_complete_avanza_chart_provides_first_bar_open_not_last_price():
    data = {"ohlc": [{"timestamp": q.instant(at).timestamp() * 1000, "open": price}
                      for at, price in [("2026-10-15T09:01:00+02:00", 100),
                                        ("2026-10-15T12:00:00+02:00", 102)]]}
    result = q.parse_avanza_open(data, INSTRUMENTS["EXAMPLE-A.ST"], NOW)
    assert result["price"] == 100
    assert result["as_of"].startswith("2026-10-15T09:01")


def test_complete_primary_skips_nasdaq_and_refreshes_even_with_cached_quotes(monkeypatch):
    def forbidden(*a):
        pytest.fail("Complete Avanza response must not query Nasdaq")
    monkeypatch.setattr(q, "fetch_nasdaq", forbidden)
    calls = []
    def primary(*args):
        calls.append(args)
        return {"latest": quote(source="Avanza"),
                "opening": quote("2026-10-15T09:00:00+02:00", 100, "Avanza")}
    cache = {"session_date": "2026-10-15", "stocks": {
        "EXAMPLE-A.ST": {"latest": quote("2026-10-15T12:45:00+02:00"),
                         "opening": quote("2026-10-15T09:00:00+02:00")}}}
    result = q.collect(cache, STOCKS, INSTRUMENTS, NOW, primary=primary)
    assert len(calls) == 1
    assert calls[0][2] is True  # Replace opening from the former primary.
    row = result["stocks"]["EXAMPLE-A.ST"]
    assert row["latest"]["source"] == row["opening"]["source"] == "Avanza"
    assert row["latest"]["change_pct"] == 2


def test_secondary_only_fills_missing_fields_without_replacing_fresh_avanza(monkeypatch):
    calls = []
    def secondary(client, instruments, now, need_open):
        calls.append((instruments, need_open))
        return {"EXAMPLE-A.ST": {"latest": quote("2026-10-15T12:45:00+02:00", 103),
                                 "opening": quote("2026-10-15T09:00:00+02:00", 100)}}, []
    monkeypatch.setattr(q, "fetch_nasdaq", secondary)
    result = q.collect({}, STOCKS, INSTRUMENTS, NOW,
                       primary=lambda *a: {"latest": quote(source="Avanza")})
    row = result["stocks"]["EXAMPLE-A.ST"]
    assert row["latest"]["source"] == "Avanza"
    assert row["opening"]["source"] == "Nasdaq"
    assert calls == [(INSTRUMENTS, True)]


def test_secondary_recovers_stale_or_failed_primary_and_preserves_cache_on_failure(monkeypatch):
    monkeypatch.setattr(q, "fetch_nasdaq", lambda *a: ({"EXAMPLE-A.ST": {"latest": quote()}}, []))
    result = q.collect({}, STOCKS, INSTRUMENTS, NOW, primary=lambda *a: {
        "latest": quote("2026-10-15T09:01:00+02:00", source="Avanza")})
    assert result["stocks"]["EXAMPLE-A.ST"]["latest"]["source"] == "Nasdaq"
    def failed(*a):
        raise q.requests.RequestException("synthetic failure")
    recovered = q.collect({}, STOCKS, INSTRUMENTS, NOW, primary=failed)
    assert recovered["stocks"]["EXAMPLE-A.ST"]["latest"]["source"] == "Nasdaq"
    monkeypatch.setattr(q, "fetch_nasdaq", failed)
    preserved = q.collect(result, STOCKS, INSTRUMENTS, NOW, primary=failed)
    assert preserved["stocks"]["EXAMPLE-A.ST"]["latest"]["price"] == 102
    assert len(preserved["errors"]) == 2


def test_closed_and_delisted_stocks_never_trigger_collection(monkeypatch):
    def forbidden(*a):
        pytest.fail("Network must not be called")
    monkeypatch.setattr(q, "fetch_nasdaq", forbidden)
    assert not q.collect({}, [{**STOCKS[0], "latest_date": "2026-10-15"}], INSTRUMENTS, NOW)["stocks"]
    assert not q.collect({}, [{**STOCKS[0], "active_for_updates": False}], INSTRUMENTS, NOW)["stocks"]


def test_publish_only_updates_disposable_branch_without_parents(monkeypatch):
    calls = []
    def git(args, **kwargs):
        calls.append(args)
        return "" if "ls-remote" in args else "abc123\n"
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setattr(q.subprocess, "check_output", git)
    q.publish({"stocks": {}})
    commit = next(call for call in calls if "commit-tree" in call)
    assert "-p" not in commit
    push = next(call for call in calls if "push" in call)
    assert push[-1].endswith(":refs/heads/intraday-cache")
    assert "--force-with-lease=refs/heads/intraday-cache:" in push
    monkeypatch.setenv("GITHUB_REF_NAME", "feature")
    with pytest.raises(ValueError):
        q.publish({})


def test_scoring_accepts_trades_that_arrive_during_collection(monkeypatch, tmp_path):
    # Synthetic clock: a batch starts before its last valid quote is received.
    from src import intraday_valuation
    times = iter([NOW, NOW + q.timedelta(minutes=3)])
    monkeypatch.setattr(q, "instant", lambda value=None: next(times))
    monkeypatch.setattr(q, "read_cache", lambda: {})
    monkeypatch.setattr(q, "read_json", lambda path: {"stocks": STOCKS} if "stocks.json" in path else INSTRUMENTS)
    output = {"session_date": "2026-10-15", "stocks": {}, "coverage": {"available": 0, "expected": 0}}
    monkeypatch.setattr(q, "collect", lambda *args: output)
    scored_at = []
    monkeypatch.setattr(intraday_valuation, "add_preliminary_scores", lambda payload, stocks, now: scored_at.append(now))
    monkeypatch.setattr("sys.argv", ["intraday", "--output", str(tmp_path / "cache.json")])
    q.main()
    assert scored_at == [NOW + q.timedelta(minutes=3)]


def test_delayed_evening_collection_only_fetches_stocks_missing_daily_close(monkeypatch):
    # Synthetic example: even a 22:00 start may recover the last intraday slot.
    now = q.instant("2026-10-15T22:00:00+02:00")
    calls = []
    def primary(instrument, *args):
        calls.append(instrument)
        return {"latest": quote("2026-10-15T17:29:00+02:00", source="Avanza"),
                "opening": quote("2026-10-15T09:01:00+02:00", 100, "Avanza")}
    def forbidden(*args):
        pytest.fail("Complete primary response must not call Nasdaq")
    monkeypatch.setattr(q, "fetch_nasdaq", forbidden)
    result = q.collect({}, STOCKS, INSTRUMENTS, now, primary=primary)
    assert len(calls) == 1
    assert result["stocks"]["EXAMPLE-A.ST"]["latest"]["price"] == 102
    calls.clear()
    result = q.collect({}, [{**STOCKS[0], "latest_date": "2026-10-15"}],
                       INSTRUMENTS, now, primary=primary)
    assert calls == []
    assert result["collection_state"] == "completed"


def test_failed_late_refresh_keeps_the_original_successful_fetch_time(monkeypatch):
    early = {"latest": {**quote(source="Avanza"), "fetched_at": NOW.isoformat()},
             "opening": quote("2026-10-15T09:01:00+02:00", 100, "Avanza")}
    before = q.collect({}, STOCKS, INSTRUMENTS, NOW, primary=lambda *args: early)
    def failed(*args):
        raise q.requests.RequestException("synthetic failure")
    monkeypatch.setattr(q, "fetch_nasdaq", failed)
    after = q.collect(before, STOCKS, INSTRUMENTS,
                      q.instant("2026-10-15T20:00:00+02:00"), primary=failed)
    assert after["stocks"]["EXAMPLE-A.ST"]["latest"]["fetched_at"] == NOW.isoformat()


def test_parsed_quotes_record_fetch_time_separately_from_trade_time():
    now = q.instant("2026-10-15T18:00:00+02:00")
    item = q.parse_avanza(avanza(), INSTRUMENTS["EXAMPLE-A.ST"], now)
    assert item["latest"]["fetched_at"] == now.isoformat()
    assert item["latest"]["as_of"] != item["latest"]["fetched_at"]
    rows = q.parse_trades(HEADER + trade("10:40:00", 101), INSTRUMENTS, now)
    assert rows["EXAMPLE-A.ST"]["latest"]["fetched_at"] == now.isoformat()
