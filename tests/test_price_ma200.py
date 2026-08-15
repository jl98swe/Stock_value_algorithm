import numpy as np
import pandas as pd

from src.fetch_data import _recalculate_ma200


def test_ma200_uses_200_closes_per_ticker():
    dates = pd.bdate_range("2025-01-01", periods=201)
    frame = pd.concat(
        [
            pd.DataFrame(
                {
                    "date": dates,
                    "open": np.arange(1, 202, dtype=float),
                    "high": np.arange(1, 202, dtype=float) + 1,
                    "low": np.arange(1, 202, dtype=float) - 1,
                    "close": np.arange(1, 202, dtype=float),
                    "volume": 1000,
                    "ticker": "AAA.ST",
                }
            ),
            pd.DataFrame(
                {
                    "date": dates,
                    "open": np.arange(101, 302, dtype=float),
                    "high": np.arange(101, 302, dtype=float) + 1,
                    "low": np.arange(101, 302, dtype=float) - 1,
                    "close": np.arange(101, 302, dtype=float),
                    "volume": 2000,
                    "ticker": "BBB.ST",
                }
            ),
        ],
        ignore_index=True,
    )

    result = _recalculate_ma200(frame)
    aaa = result.loc[result["ticker"] == "AAA.ST"].reset_index(drop=True)
    bbb = result.loc[result["ticker"] == "BBB.ST"].reset_index(drop=True)

    assert aaa.loc[:198, "ma200"].isna().all()
    assert bbb.loc[:198, "ma200"].isna().all()
    assert aaa.loc[199, "ma200"] == np.mean(np.arange(1, 201, dtype=float))
    assert aaa.loc[200, "ma200"] == np.mean(np.arange(2, 202, dtype=float))
    assert bbb.loc[199, "ma200"] == np.mean(np.arange(101, 301, dtype=float))
