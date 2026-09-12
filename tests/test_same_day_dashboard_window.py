import json

from src.add_report import _same_day_effective_date
from src.limit_dashboard_window import limit_dashboard


def test_same_day_effective_date_uses_stockholm_calendar_day():
    assert _same_day_effective_date("2026-07-17T07:00:00+02:00") == "2026-07-17"
    assert _same_day_effective_date("2026-07-17T22:30:00+00:00") == "2026-07-18"


def test_dashboard_window_keeps_only_global_start_and_later(tmp_path):
    target = tmp_path / "dashboard.json"
    target.write_text(
        json.dumps(
            {
                "meta": {},
                "stocks": {
                    "TEST.ST": {
                        "candles": [
                            {"date": "2019-08-30", "close": 99},
                            {"date": "2019-09-02", "close": 100},
                        ],
                        "scores": [
                            {"date": "2019-08-30", "value": 50},
                            {"date": "2019-09-02", "value": 51},
                        ],
                        "signals": [
                            {"date": "2019-08-30", "side": "BUY"},
                            {"date": "2019-09-02", "side": "SELL"},
                        ],
                        "closed_trades": [
                            {"entry_date": "2019-08-30", "exit_date": "2019-09-05"},
                            {"entry_date": "2019-09-02", "exit_date": "2019-09-05"},
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = limit_dashboard(target, start_date="2019-09-02")
    stock = payload["stocks"]["TEST.ST"]

    assert [row["date"] for row in stock["candles"]] == ["2019-09-02"]
    assert [row["date"] for row in stock["scores"]] == ["2019-09-02"]
    assert [row["date"] for row in stock["signals"]] == ["2019-09-02"]
    assert [row["entry_date"] for row in stock["closed_trades"]] == ["2019-09-02"]
    assert payload["meta"]["frontend_start_date"] == "2019-09-02"
