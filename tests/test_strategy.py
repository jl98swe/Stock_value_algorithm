import pandas as pd

from src.strategy import run_strategy


def test_two_buys_require_rearm_and_five_trading_days():
    dates = pd.bdate_range("2026-01-02", periods=10)
    frame = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 10,
            "Close": [100.0] * 10,
            # Första köp idx 1. Score lämnar 0 på idx 3, återkommer idx 4,
            # men får inte signalera igen förrän idx 6 (= fem handelssteg senare).
            "Score": [50.0, 0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 20.0, 100.0, 50.0],
            "FundamentalLock": [False] * 10,
            "LockReason": [""] * 10,
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
    assert buy_signals[1]["signal_date"] == dates[6].date().isoformat()
    assert buy_signals[1]["execution_date"] == dates[7].date().isoformat()

    assert len(sell_signals) == 1
    assert sell_signals[0]["signal_date"] == dates[8].date().isoformat()
    assert sell_signals[0]["execution_date"] == dates[9].date().isoformat()
    assert result["summary"]["active_lots"] == 1


def test_fundamental_lock_blocks_without_consuming_buy_boundary():
    dates = pd.bdate_range("2026-02-02", periods=4)
    frame = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 4,
            "Close": [100.0] * 4,
            "Score": [50.0, 0.0, 0.0, 20.0],
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
