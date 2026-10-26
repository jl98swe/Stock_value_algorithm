from __future__ import annotations

import pandas as pd

from src import audit_quarterly_eps_readiness


def test_universe_excludes_delisted_tickers(monkeypatch):
    monkeypatch.setattr(
        audit_quarterly_eps_readiness,
        "load_price_history",
        lambda: pd.DataFrame({"ticker": ["COOR.ST", "VIVA.ST", "COOR.ST"]}),
    )
    monkeypatch.setattr(
        audit_quarterly_eps_readiness,
        "active_tickers",
        lambda tickers: [ticker for ticker in tickers if ticker != "VIVA.ST"],
    )

    assert audit_quarterly_eps_readiness._universe() == ["COOR.ST"]
