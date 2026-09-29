import json
from pathlib import Path

import pandas as pd

from src.pipeline import _display_name

ROOT = Path(__file__).parents[1]


def test_display_names_use_company_metadata_and_preserve_unknown_ticker_fallback():
    assert _display_name('EMBRAC-B.ST') == 'Embracer'
    assert _display_name('ANOD-B.ST') == 'Addnode'
    assert 'Platzer' in _display_name('PLAZ-B.ST')
    assert _display_name('UNKNOWN-B.ST') == 'UNKNOWN B'


def test_export_and_source_metadata_have_names_for_every_listed_stock():
    stocks = json.loads((ROOT / 'docs/data/stocks.json').read_text())['stocks']
    metadata = pd.read_csv(ROOT / 'data/metadata/stocks_yahoo.csv')
    source = pd.read_csv(ROOT / 'data/metadata/stocks.csv')
    mapping = pd.read_csv(ROOT / 'config/ticker_mapping.csv')
    source_names = dict(zip(source['ticker'], source['company']))
    source_tickers = dict(zip(mapping['yahoo_ticker'], mapping['borsdata_ticker']))
    names = dict(zip(metadata['ticker'], metadata['company']))
    for stock in stocks:
        ticker = stock['ticker']
        assert names[ticker] and pd.notna(names[ticker])
        assert stock['name'] == names[ticker] == _display_name(ticker)
        assert source_names[source_tickers[ticker]] == names[ticker]
