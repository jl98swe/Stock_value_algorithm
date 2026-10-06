from src.strategy_overviews import write_strategy_overviews, STRATEGIES


def test_export_has_shared_trading_dates_and_no_cross_strategy_position_fallback(tmp_path):
    live = {key:{"position":{"lots":i},"signals":[],"next_action":{"type":"NONE"},"strategy_filter":{"buy_allowed":True}}
            for i,key in enumerate(STRATEGIES)}
    stock = {"latest":{"score":50},"candles":[{"date":f"2026-01-{day:02}"} for day in range(1,31)],"strategies":live}
    out = write_strategy_overviews({"TEST":stock},{"generated_at":"now","rules":{"buy_score":1}},tmp_path / "overview.json")
    assert len(out["meta"]["trading_dates"]) == 20
    assert out["meta"]["trading_dates"][0] == "2026-01-11"
    for i,key in enumerate(STRATEGIES):
        assert out["strategies"][key]["stocks"]["TEST"]["position"]["lots"] == i
        assert "candles" not in out["strategies"][key]["stocks"]["TEST"]
