"""Verified publication timing, independent of EPS priority and calendar estimates."""
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import exchange_calendars as xcals
import pandas as pd
from .config import ROOT

PUBLICATIONS = ROOT / 'data/fundamentals/report_publications.csv'
AFTER_CLOSE_NOTE = 'Rapporten publicerades efter börsstängning och används därför från nästa handelsdag.'


@lru_cache(maxsize=1024)
def publication_session(published_at, report_date=None) -> tuple[pd.Timestamp, bool]:
    """First XSTO closing valuation with this information (including half days)."""
    at = pd.Timestamp(published_at)
    if at.tzinfo is None:
        raise ValueError('Publication timestamp must include a timezone')
    day = at.tz_convert('Europe/Stockholm').tz_localize(None).normalize()
    calendar = xcals.get_calendar('XSTO', start=day - pd.Timedelta(days=10),
                                  end=day + pd.Timedelta(days=15))
    session = calendar.date_to_session(day, direction='next')
    unavailable_at_close = calendar.is_session(day) and at >= calendar.session_close(day)
    official_day = pd.Timestamp(report_date).normalize() if report_date is not None else day
    # Official issuer date can precede the Stockholm civil date after midnight.
    close_day = calendar.date_to_session(official_day, direction='previous')
    after_close = at >= calendar.session_close(close_day)
    if unavailable_at_close:
        session = calendar.next_session(session)
    return pd.Timestamp(session).tz_localize(None).normalize(), bool(after_close)


def apply_publications(reports: pd.DataFrame, path: Path = PUBLICATIONS) -> pd.DataFrame:
    result = reports.copy()
    if not path.exists():
        return result
    evidence = pd.read_csv(path, dtype=str).fillna('')
    if evidence.duplicated(['ticker', 'report_period']).any():
        raise ValueError('Duplicate verified publication')
    from .report_date_revisions import _date_mask
    for row in evidence.itertuples(index=False):
        at = pd.Timestamp(row.published_at)
        effective, _ = publication_session(at, row.report_date)
        day = pd.Timestamp(row.report_date).normalize()
        if day != at.tz_localize(None).normalize():
            raise ValueError(f'Publication/report date mismatch: {row.ticker} {row.report_period}')
        if not row.source.strip():
            raise ValueError('Verified publication requires a source')
        mask = _date_mask(result, row.ticker, row.report_period, include_aliases=True)
        result.loc[mask, 'published_at'] = at.tz_convert('UTC')
        result.loc[mask, 'report_date'] = day
        result.loc[mask, 'effective_date'] = effective
        result.loc[mask, 'publication_time_verified'] = True
    return result


def publication_metadata(row) -> dict:
    verified = str(row.get('publication_time_verified', False)).lower() in {'true', '1'}
    at = pd.to_datetime(row.get('published_at'), utc=True, errors='coerce')
    day = pd.to_datetime(row.get('report_date'), errors='coerce')
    if pd.isna(day) and pd.notna(at):
        day = at.tz_convert('Europe/Stockholm').tz_localize(None).normalize()
    if pd.isna(day):
        day = pd.to_datetime(row.get('effective_date'), errors='coerce')
    after = publication_session(at, day)[1] if verified and pd.notna(at) else False
    return {'report_date': day.date().isoformat() if pd.notna(day) else None,
            'published_at': at.isoformat() if pd.notna(at) else None,
            'publication_time_verified': verified,
            'published_after_close': after,
            'publication_note': AFTER_CLOSE_NOTE if after else None}
