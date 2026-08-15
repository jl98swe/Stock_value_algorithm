import json

from src.add_report import _same_day_effective_date
from src.limit_dashboard_window import limit_dashboard


def test_same_day_effective_date_uses_stockholm_calendar_day():
    assert _same_day_effective_date("2026-07-17T07:00:00+02:00") == "2026-07-17"
    assert _same_day_effective_date("2026-07-17T22:30:00+00:00") == "2026-07-18"


def test_dashboard_window_keeps_only_2024_and_later(tmp_path):
    target = tmp_path / "dashboard.json"
    target.write_text(
        json.dumps(
            {
                "meta": {},
                "stocks": {
                    "TEST.ST": {
                        "candles": [
                            {"date": "2023-12-29", "close": 99},
                            {"date": "2024-01-02", "close": 100},
                        ],
                        "scores": [
                            {"date": "2023-12-29", "value": 50},
                            {"date": "2024-01-02", "value": 51},
                        ],
                        "signals": [
                            {"date": "2023-12-29", "side": "BUY"},
                            {"date": "2024-01-02", "side": "SELL"},
                        ],
                        "closed_trades": [
                            {"entry_date": "2023-12-29", "exit_date": "2024-01-05"},
                            {"entry_date": "2024-01-02", "exit_date": "2024-01-05"},
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = limit_dashboard(target, start_date="2024-01-01")
    stock = payload["stocks"]["TEST.ST"]

    assert [row["date"] for row in stock["candles"]] == ["2024-01-02"]
    assert [row["date"] for row in stock["scores"]] == ["2024-01-02"]
    assert [row["date"] for row in stock["signals"]] == ["2024-01-02"]
    assert [row["entry_date"] for row in stock["closed_trades"]] == ["2024-01-02"]
    assert payload["meta"]["frontend_start_date"] == "2024-01-01"
