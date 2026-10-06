"""Stop live collection after delisting while retaining the historical universe."""
from pathlib import Path

import pandas as pd

from .config import ROOT

STATUS_FILE = ROOT / "data/metadata/listing_status.csv"


def last_trading_dates(path: Path = STATUS_FILE) -> dict[str, pd.Timestamp]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if frame.ticker.duplicated().any():
        raise ValueError("Dubbla tickers i noteringsstatus")
    dates = pd.to_datetime(frame.last_trading_date, errors="raise")
    return dict(zip(frame.ticker.astype(str), dates, strict=True))


def active_tickers(tickers, *, today=None, path: Path = STATUS_FILE) -> list[str]:
    day = pd.Timestamp(today) if today is not None else pd.Timestamp.now(tz="Europe/Stockholm")
    day = day.tz_localize(None).normalize()
    ended = last_trading_dates(path)
    return [str(t) for t in tickers if str(t) not in ended or day <= ended[str(t)]]


def trading_rows(frame: pd.DataFrame, *, path: Path = STATUS_FILE) -> pd.DataFrame:
    result = frame.copy()
    for ticker, last in last_trading_dates(path).items():
        result = result.loc[~(result.ticker.eq(ticker) & pd.to_datetime(result.date).gt(last))]
    return result
