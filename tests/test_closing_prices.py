"""Synthetic examples for two independently collected source snapshots."""
import copy
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.closing_prices import apply_snapshot, collect
from src import closing_prices as closing

NOW = datetime.fromisoformat("2026-10-19T18:30:00+02:00")
STOCKS = [{"ticker":"EXAMPLE.ST", "active_for_updates":True},
          {"ticker":"ENDED.ST", "active_for_updates":False}]


def row(close=105., fetched="2026-10-19T18:31:00+02:00"):
    return {"ticker":"EXAMPLE.ST", "date":"2026-10-19", "open":100., "high":110.,
            "low":95., "close":close, "volume":1000., "fetched_at":fetched}


def snapshot(source, close=105., fetched="2026-10-19T18:31:00+02:00"):
    return {"source":source, "session_date":"2026-10-19", "started_at":NOW.isoformat(),
            "rows":[row(close, fetched)]}


@pytest.fixture
def paths(tmp_path):
    base = tmp_path / "base.parquet"
    pd.DataFrame([{**row(100.), "date":"2026-10-16"}]).to_parquet(base)
    return {"base_file":base, "updates_file":tmp_path/"updates.csv",
            "provenance_file":tmp_path/"sources.csv", "now":NOW}


@pytest.mark.parametrize("order", [("Yahoo","Avanza"),("Avanza","Yahoo")])
def test_overlapping_sources_always_end_with_yahoo_but_avanza_can_fill_first(paths, order):
    reports=[]
    for source in order:
        reports.append(apply_snapshot(snapshot(source, 105. if source=="Yahoo" else 104.), **paths))
    prices=pd.read_csv(paths["updates_file"])
    assert prices.close.iloc[-1] == 105.
    assert pd.read_csv(paths["provenance_file"]).source.iloc[-1] == "Yahoo"
    assert reports[-1]["differences"][0]["delta"] != 0
    if order[0] == "Avanza":
        assert reports[0]["applied"] == reports[1]["applied"] == 1
        assert reports[1]["recalculate_from"] == {"EXAMPLE.ST":"2026-10-19"}
    else:
        assert reports[1]["applied"] == 0
        assert reports[1]["kept"] == 1


def test_late_completion_of_older_same_source_response_cannot_replace_newer(paths):
    apply_snapshot(snapshot("Avanza",106.), **paths)
    result=apply_snapshot(snapshot("Avanza",104.,"2026-10-19T18:30:00+02:00"), **paths)
    assert result["kept"] == 1
    assert pd.read_csv(paths["updates_file"]).close.iloc[-1] == 106.


def test_preexisting_daily_prices_without_provenance_are_not_overwritten_by_avanza(paths):
    pd.DataFrame([row(108.)]).to_csv(paths["updates_file"],index=False)
    result=apply_snapshot(snapshot("Avanza",104.),**paths)
    assert result["kept"] == 1
    assert pd.read_csv(paths["updates_file"]).close.iloc[-1] == 108.
    assert paths["provenance_file"].exists()


@pytest.mark.parametrize("bad",["yesterday","missing","ohlc","before_close","wrong_session"])
def test_bad_snapshot_never_changes_price_history(paths,bad):
    s=snapshot("Yahoo")
    if bad=="yesterday":s["rows"][0]["date"]="2026-10-16"
    if bad=="missing":s["rows"][0]["open"]=None
    if bad=="ohlc":s["rows"][0]["low"]=109.
    if bad=="before_close":s["started_at"]="2026-10-19T17:00:00+02:00"
    if bad=="wrong_session":s["session_date"]="2026-10-16"
    with pytest.raises(ValueError):apply_snapshot(s,**paths)
    assert not paths["updates_file"].exists()


def test_both_sources_collect_today_even_when_daily_prices_already_published():
    stocks=[{**STOCKS[0],"latest_date":"2026-10-19"},STOCKS[1]]
    calls=[]
    def yahoo(tickers,**kwargs):
        calls.append(tickers)
        return pd.DataFrame([row(),{**row(),"date":"2026-10-16"}])
    first=collect("Yahoo","17:30",now=NOW,stocks=stocks,yahoo=yahoo)
    second=collect("Avanza","18:30",now=NOW,stocks=stocks,
                   instruments={"EXAMPLE.ST":{}},avanza=lambda *args:row(104.))
    assert calls == [["EXAMPLE.ST"]]
    assert first["available"] == second["available"] == 1
    assert first["rows"][0]["timing_scope"] == "batch"
    assert second["rows"][0]["timing_scope"] == "instrument"


def test_collection_before_close_never_downloads_or_uses_yesterdays_data():
    def forbidden(*a,**k):pytest.fail("No download before close")
    result=collect("Yahoo","17:30",now=datetime.fromisoformat("2026-10-20T09:00:00+02:00"),
                   stocks=STOCKS,yahoo=forbidden)
    assert result["state"] == "not_due"
    assert not result["rows"]


def test_daily_workflows_have_independent_collection_and_only_serialize_publication():
    root=Path(__file__).parents[1]/".github/workflows"
    w=yaml.safe_load((root/"daily_update.yml").read_text())
    assert "concurrency" not in w
    assert "concurrency" not in w["jobs"]["collect"]
    assert w["jobs"]["update"]["needs"] == "collect"
    assert w["jobs"]["update"]["concurrency"]["group"] == "stock-data-${{ github.ref }}"
    assert w.get("on",w.get(True))["schedule"] == [{"cron":"30 17 * * 1-5","timezone":"Europe/Stockholm"}, {"cron":"15 13 * * 1-5","timezone":"Europe/Stockholm"}]
    a=yaml.safe_load((root/"avanza_closing.yml").read_text())
    assert a.get("on",a.get(True))["schedule"] == [{"cron":"30 18 * * 1-5","timezone":"Europe/Stockholm"}, {"cron":"0 14 * * 1-5","timezone":"Europe/Stockholm"}]
    assert a["jobs"]["daily"]["with"]["source"] == "Avanza"


def test_avanza_daily_bar_uses_real_ohlc_and_does_not_invent_missing_volume(monkeypatch):
    now=NOW
    instrument={"avanza_id":"test","isin":"SYNTHETIC","currency":"SEK","avanza_symbol":"EXAMPLE"}
    data={"isin":"SYNTHETIC","listing":{"currency":"SEK","tickerSymbol":"EXAMPLE"},
          "quote":{"last":105.,"highest":110.,"lowest":95.,
                   "timeOfLast":int(datetime.fromisoformat("2026-10-19T17:29:59+02:00").timestamp()*1000)}}
    chart={"ohlc":[{"timestamp":int(datetime.fromisoformat("2026-10-19T09:00:00+02:00").timestamp()*1000),"open":100.}]}
    answers=iter([data,chart])
    class Response:
        def raise_for_status(self):pass
        def json(self):return next(answers)
    class Client:
        headers={}
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,*a,**k):return Response()
    monkeypatch.setattr(closing.requests,"Session",Client)
    monkeypatch.setattr(closing,"instant",lambda:now)
    result=closing.fetch_avanza_daily(instrument,now)
    assert [result[k] for k in ["open","high","low","close"]] == [100.,110.,95.,105.]
    assert result["volume"] is None

@pytest.mark.parametrize('date,time,expected', [('2026-04-02','12:59:59',False),('2026-04-02','13:15:00',True),('2026-04-02','14:00:00',True),('2026-04-01','13:15:00',False),('2026-04-01','20:00:00',False),('2026-04-03','14:00:00',False)])
@pytest.mark.parametrize('source', ['Yahoo','Avanza'])
def test_calendar_controls_early_closing_collection(date,time,expected,source):
    calls=[]
    def yahoo(*a,**k):
        calls.append(source)
        return pd.DataFrame([{**row(),'date':date}])
    def avanza(*a):
        calls.append(source)
        return row()
    result=collect(source,'13:15',now=datetime.fromisoformat(date+'T'+time+'+02:00'),stocks=STOCKS,
                   instruments={'EXAMPLE.ST':{}},yahoo=yahoo,avanza=avanza)
    assert bool(calls) is expected
    assert bool(result['rows']) is expected
