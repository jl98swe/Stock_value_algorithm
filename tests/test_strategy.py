import pandas as pd

from src.strategy import run_strategy


def test_only_one_position_can_be_active_per_stock():
    dates = pd.bdate_range("2026-01-02", periods=12)
    frame = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 12,
            "Close": [100.0] * 12,
            # Det andra köpläget ignoreras medan positionen är aktiv. Efter
            # försäljningen får en ny position öppnas i en ny cykel.
            "Score": [50.0, 0.999, 0.999, 20.0, 0.999, 0.999, 0.999, 20.0, 99.001, 50.0, 0.999, 20.0],
            "FundamentalLock": [False] * 12,
            "LockReason": [""] * 12,
        }
    )

    result = run_strategy(frame, "TEST.ST")
    buy_signals = [
        signal
        for signal in result["signals"]
        if signal["side"] == "BUY" and signal["status"] == "executed"
    ]
    sell_signals = [
        signal
        for signal in result["signals"]
        if signal["side"] == "SELL" and signal["status"] == "executed"
    ]

    assert len(buy_signals) == 2
    assert buy_signals[0]["signal_date"] == dates[1].date().isoformat()
    assert buy_signals[0]["execution_date"] == dates[2].date().isoformat()
    assert buy_signals[1]["signal_date"] == dates[10].date().isoformat()
    assert buy_signals[1]["execution_date"] == dates[11].date().isoformat()

    assert len(sell_signals) == 1
    assert sell_signals[0]["signal_date"] == dates[8].date().isoformat()
    assert sell_signals[0]["execution_date"] == dates[9].date().isoformat()
    assert result["summary"]["active_lots"] == 1
    assert result["state"]["PositionLots"].max() == 1
    assert any(signal["status"] == "suppressed_capacity" for signal in result["signals"])


def test_fundamental_lock_blocks_without_consuming_buy_boundary():
    dates = pd.bdate_range("2026-02-02", periods=4)
    frame = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 4,
            "Close": [100.0] * 4,
            "Score": [50.0, 0.999, 0.999, 20.0],
            "FundamentalLock": [False, True, False, False],
            "LockReason": ["", "Ogranskad regulatorisk nyhet", "", ""],
        }
    )

    result = run_strategy(frame, "TEST.ST")
    blocked = [signal for signal in result["signals"] if signal["status"] == "blocked"]
    executed = [signal for signal in result["signals"] if signal["status"] == "executed"]

    assert len(blocked) == 1
    assert blocked[0]["signal_date"] == dates[1].date().isoformat()
    assert len(executed) == 1
    assert executed[0]["side"] == "BUY"
    assert executed[0]["signal_date"] == dates[2].date().isoformat()
    assert executed[0]["execution_date"] == dates[3].date().isoformat()
