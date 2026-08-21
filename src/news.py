"""Fetch and curate company press releases from MFN.

This module is intentionally independent of EPS/fundamental ingestion. It writes
only compact news metadata to ``data/raw/news`` (items shown as N events) and a
separate review queue for ambiguous releases.

The public MFN company pages are used because MFN documents that mfn.se provides
streamed press releases and historical releases for listed Nordic companies,
while no public developer API is documented. The scraper therefore avoids
private endpoints and is deliberately defensive about HTML changes.
"""

from __future__ import annotations

import argparse
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup, Tag

from .config import ROOT
from .events import enrich_news, load_reviews, stable_event_id
from .utils import read_json, write_json_atomic

MFN_BASE = "https://mfn.se"
NEWS_ROOT = ROOT / "data" / "raw" / "news"
NEWS_META_ROOT = ROOT / "data" / "news"
SOURCE_MAP_FILE = NEWS_META_ROOT / "mfn_sources.csv"
REVIEW_QUEUE_FILE = NEWS_META_ROOT / "review_queue.json"
STATUS_FILE = NEWS_META_ROOT / "status.json"
STOCK_METADATA_FILE = ROOT / "data" / "metadata" / "stocks_yahoo.csv"
STOCKS_JSON = ROOT / "docs" / "data" / "stocks.json"
EVENTS_JSON = ROOT / "docs" / "data" / "events.json"
DEFAULT_START = date(2024, 1, 1)
STOCKHOLM = ZoneInfo("Europe/Stockholm")
HTTP_TIMEOUT = (8, 30)
REQUEST_DELAY_SECONDS = 0.15
MAX_SUMMARY_CHARS = 650

DATE_RE = re.compile(r"(?P<date>20\d{2}-\d{2}-\d{2})(?:[ T](?P<time>\d{2}:\d{2}(?::\d{2})?))?")
ARTICLE_PATH_RE = re.compile(r"^/(?:[^/]+/)?a/(?P<slug>[^/]+)/(?P<article>[^/?#]+?)(?:\.iframe)?/?$")

LEGAL_TOKENS = {
    "ab", "publ", "plc", "oyj", "asa", "as", "ltd", "inc", "aktiebolag",
    "class", "share", "shares", "ser", "serie", "sdb",
}
SHARE_CLASS_TOKENS = {"a", "b", "c", "d"}

# Report and dividend events already have dedicated E/D representations.
REPORT_PATTERNS = (
    r"\bdelårsrapport\b", r"\bkvartalsrapport\b", r"\bbokslutskommunik[eé]\b",
    r"\bårsredovisning\b", r"\bårsrapport\b", r"\binterim report\b",
    r"\bquarter(?:ly)? report\b", r"\byear[- ]end report\b", r"\bannual report\b",
    r"\bfinancial report\b", r"\bq[1-4]\s+20\d{2}\s+(?:report|results)\b",
    r"\bresults? for (?:the )?(?:first|second|third|fourth) quarter\b",
    r"\binvitation to (?:presentation|conference call).*(?:report|results)\b",
    r"\btelefonkonferens.*(?:rapport|resultat)\b",
)
DIVIDEND_ROUTINE_PATTERNS = (
    r"\bex[- ]?dividend\b", r"\bx[- ]?dag\b.*\butdelning\b",
    r"\bkontantutdelning\b", r"\bcash dividend\b", r"\bdividend proposal\b",
    r"\bproposed dividend\b", r"\butdelningsförslag\b",
)
ROUTINE_PATTERNS = (
    r"\bkallelse till (?:års|extra )?bolagsstämma\b", r"\bkallelse till (?:extra )?årsstämma\b",
    r"\bnotice of (?:annual|extraordinary) general meeting\b",
    r"\bkommunik[eé] från (?:års|extra )?bolagsstämma\b", r"\bkommunik[eé] från (?:extra )?årsstämma\b",
    r"\bminutes (?:from|of) (?:the )?(?:annual|extraordinary) general meeting\b",
    r"\bvalberedning\b", r"\bnomination committee\b",
    r"\bmanagers?' transactions?\b", r"\bledande befattningshavares transaktion\b",
    r"\bnotification of major holdings?\b", r"\bflaggningsmeddelande\b", r"\bflaggemelding\b",
    r"\btotal number of (?:shares|voting rights)\b", r"\bantal aktier och röster\b",
    r"\btransactions? made under (?:the )?share buyback program\b",
    r"\båterköp av (?:egna )?aktier.*vecka\b", r"\bbuyback of (?:own )?shares?.*\bweek\b",
    r"\bshare repurchase(?:s)? .*\bweek\b",
    r"\bfinancial calendar\b", r"\bfinansiell kalender\b",
    r"\binvitation to (?:capital markets day|presentation)\b", r"\binbjudan till (?:kapitalmarknadsdag|presentation)\b",
    r"\bparticipat(?:es|ing) at\b.*\bconference\b", r"\bdeltar på\b.*\bkonferens\b",
    r"\baward(?:ed)?\b.*\bpartner award\b", r"\butsedd till vinnare\b.*\baward\b",
)

HIGH_MATERIAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("profit_warning", (
        r"\bvinstvarn", r"\bprofit warning\b", r"\breverse profit warning\b",
        r"\bomvänd vinstvarn", r"\bpreliminary results?\b", r"\bpreliminärt resultat\b",
    )),
    ("guidance", (
        r"\bguidance\b", r"\bprognos\b", r"\boutlook\b", r"\bfinansiella mål\b",
        r"\bfinancial targets?\b", r"\blowers? (?:its )?forecast\b", r"\braises? (?:its )?forecast\b",
    )),
    ("acquisition", (
        r"\bförvärv", r"\bacqui(?:res?|sition)\b", r"\btakeover\b", r"\buppköp\b",
        r"\bdivest", r"\bavyttr", r"\bsells? (?:its |the )?(?:business|subsidiary|division)\b",
    )),
    ("capital", (
        r"\bföreträdesemission\b", r"\brights issue\b", r"\bdirected share issue\b",
        r"\briktad emission\b", r"\bprivate placement\b", r"\bcapital raise\b",
        r"\brekapitaliser", r"\brefinanc", r"\bcovenant\b", r"\bliquidity\b", r"\blikviditet\b",
    )),
    ("regulatory", (
        r"\bfda\b", r"\bema\b", r"\bregulatory approval\b", r"\bmarketing authori[sz]ation\b",
        r"\bmyndighetsgodkännande\b", r"\bgodkännande från\b", r"\bfast track designation\b",
        r"\bclinical hold\b", r"\bregulatorisk\b",
    )),
    ("legal", (
        r"\blawsuit\b", r"\blitigation\b", r"\binvestigation\b", r"\bprobe\b", r"\bsanction\b",
        r"\bstämning\b", r"\brättsprocess\b", r"\butredning\b", r"\bböter\b",
    )),
    ("restructuring", (
        r"\bimpairment\b", r"\bnedskriv", r"\brestructur", r"\bomstruktur",
        r"\bredundan", r"\bvarsel\b", r"\blayoff", r"\bworkforce reduction\b",
    )),
    ("leadership", (
        r"\bnew ceo\b", r"\bappoints? .*\bceo\b", r"\bceo .*resign", r"\bchief executive .*resign",
        r"\bny vd\b", r"\bvd .*avgår\b", r"\bvd-byte\b", r"\bnew cfo\b", r"\bcfo .*resign",
        r"\bny cfo\b", r"\bcfo .*avgår\b", r"\bnew chair", r"\bny styrelseordförande\b",
    )),
    ("distress", (
        r"\bbankrupt", r"\binsolven", r"\breconstruction\b", r"\brekonstruktion\b",
        r"\bgoing concern\b", r"\bbetalningssvår", r"\bdefault\b",
    )),
    ("dividend_change", (
        r"\bcancel(?:s|led)? (?:the )?dividend\b", r"\bsuspend(?:s|ed)? (?:the )?dividend\b",
        r"\bwithdraw(?:s|n)? (?:the )?dividend\b", r"\bindragen utdelning\b",
        r"\bställer in utdelning\b", r"\bchanges? dividend policy\b", r"\bändrar utdelningspolicy\b",
    )),
)

COMMERCIAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("order", (r"\border\b", r"\bbeställning\b", r"\border värd\b")),
    ("contract", (r"\bcontract\b", r"\bagreement\b", r"\bavtal\b", r"\bramavtal\b", r"\bframework agreement\b")),
    ("partnership", (r"\bpartnership\b", r"\bpartnerskap\b", r"\bcollaboration\b", r"\bsamarbete\b")),
)
MATERIALITY_QUALIFIERS = (
    r"\bmajor\b", r"\bsignificant\b", r"\bmaterial\b", r"\bstrategic\b", r"\brecord\b",
    r"\bstörre\b", r"\bbetydande\b", r"\bstrategisk\b", r"\brekord",
    r"\b(?:sek|msek|mnsek|eur|meur|usd|musd|gbp|nok|mnok)\s*[0-9]",
    r"\b[0-9][0-9., ]*\s*(?:million|miljon|billion|miljard)\b",
)
REGULATORY_MARKERS = (
    "inside information", "insiderinformation", "informationen är sådan som",
    "regulatory press release", "regulatoriskt pressmeddelande", "regulatorisk information",
    "market abuse regulation", "artikel 17 i mar", "article 17 of mar",
)

SWEDISH_HINTS = {"och", "för", "från", "med", "bolaget", "har", "tecknar", "förvärvar", "offentliggör", "utser", "vd"}
ENGLISH_HINTS = {"and", "for", "from", "with", "company", "has", "signs", "acquires", "announces", "appoints", "ceo"}


@dataclass(frozen=True)
class StockIdentity:
    ticker: str
    company: str


@dataclass(frozen=True)
class Relevance:
    status: str
    topic: str
    reason: str


class MFNClient:
    def __init__(self, *, delay: float = REQUEST_DELAY_SECONDS) -> None:
        self.delay = max(0.0, float(delay))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "StockValueAlgorithm/1.0 (+https://github.com/jl98swe/Stock_value_algorithm)",
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            }
        )
        self._last_request = 0.0

    def get(self, url: str, *, params: dict[str, str] | None = None) -> requests.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=HTTP_TIMEOUT, allow_redirects=True)
                self._last_request = time.monotonic()
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response
            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else 0
                if status and status < 500 and status != 429:
                    raise
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        assert last_error is not None
        raise last_error


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _slugify(value: str) -> str:
    return _normalize_text(value).replace(" ", "-")


def _company_tokens(value: str) -> list[str]:
    tokens = [token for token in _normalize_text(value).split() if token not in LEGAL_TOKENS]
    while tokens and tokens[-1] in SHARE_CLASS_TOKENS:
        tokens.pop()
    return [token for token in tokens if len(token) > 1]


def _company_similarity(expected: str, actual: str) -> float:
    left = _company_tokens(expected)
    right = _company_tokens(actual)
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    if not shared:
        return 0.0
    return max(
        len(shared) / max(1, min(len(set(left)), len(set(right)))),
        SequenceMatcher(None, " ".join(left), " ".join(right)).ratio(),
    )


def _company_name_from_page(soup: BeautifulSoup) -> str:
    for selector in ("h1", "meta[property='og:site_name']", "title"):
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content", "") if node.name == "meta" else node.get_text(" ", strip=True)
        value = re.sub(r"^MFN\.se\s*>\s*", "", value, flags=re.I)
        value = re.sub(r"\s*[-|·].*$", "", value).strip()
        if value:
            return value
    return ""


def _candidate_slugs(company: str, ticker: str) -> list[str]:
    candidates: list[str] = []
    core_tokens = _company_tokens(company.strip())
    ticker_stem = ticker.removesuffix(".ST").replace("-", " ")
    variants = [company.strip(), " ".join(core_tokens), ticker_stem]
    if core_tokens:
        variants.extend(
            [
                f"{' '.join(core_tokens)} group",
                f"{' '.join(core_tokens)} holding",
                f"{' '.join(core_tokens)} ab",
            ]
        )
    for value in variants:
        slug = _slugify(value)
        if slug and slug not in candidates:
            candidates.append(slug)
    return candidates


def _extract_company_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        parsed = urlparse(urljoin(MFN_BASE, str(anchor.get("href", ""))))
        parts = [part for part in parsed.path.split("/") if part]
        slug = ""
        if len(parts) == 3 and parts[0] in {"all", "pr"} and parts[1] == "a":
            slug = parts[2]
        elif len(parts) == 2 and parts[0] == "pr":
            slug = parts[1]
        if not slug:
            continue
        label = anchor.get_text(" ", strip=True)
        if label:
            output.append((slug.replace(".iframe", ""), label))
    return output


def _discover_by_search(client: MFNClient, company: str) -> list[str]:
    candidates: list[str] = []
    try:
        base = client.get(f"{MFN_BASE}/a/")
    except requests.RequestException:
        return candidates
    soup = BeautifulSoup(base.text, "html.parser")
    attempts: list[tuple[str, dict[str, str]]] = []
    for form in soup.find_all("form"):
        text_inputs = [
            item for item in form.find_all("input")
            if str(item.get("type", "text")).lower() in {"text", "search", ""}
            and item.get("name")
        ]
        for field in text_inputs:
            hint = " ".join(str(field.get(key, "")) for key in ("placeholder", "aria-label", "name", "id")).casefold()
            if not any(token in hint for token in ("filtr", "keyword", "search", "sök", "query")):
                continue
            params: dict[str, str] = {}
            for hidden in form.find_all("input", attrs={"type": "hidden"}):
                if hidden.get("name"):
                    params[str(hidden["name"])] = str(hidden.get("value", ""))
            params[str(field["name"])] = company
            attempts.append((urljoin(base.url, str(form.get("action") or base.url)), params))
    for key in ("q", "query", "search", "keyword"):
        attempts.append((f"{MFN_BASE}/a/", {key: company}))

    seen_requests: set[str] = set()
    for url, params in attempts[:8]:
        key = f"{url}?{urlencode(sorted(params.items()))}"
        if key in seen_requests:
            continue
        seen_requests.add(key)
        try:
            response = client.get(url, params=params)
        except requests.RequestException:
            continue
        for slug, label in _extract_company_links(BeautifulSoup(response.text, "html.parser")):
            if _company_similarity(company, label) >= 0.55 and slug not in candidates:
                candidates.append(slug)
    return candidates


def _verify_company_slug(client: MFNClient, company: str, slug: str) -> tuple[bool, str, str]:
    url = f"{MFN_BASE}/all/a/{slug}"
    try:
        response = client.get(url)
    except requests.RequestException:
        return False, url, ""
    soup = BeautifulSoup(response.text, "html.parser")
    actual = _company_name_from_page(soup)
    return bool(actual) and _company_similarity(company, actual) >= 0.52, response.url, actual


def _load_source_map() -> pd.DataFrame:
    columns = ["ticker", "company", "mfn_slug", "mfn_url", "status", "last_checked"]
    if not SOURCE_MAP_FILE.exists() or SOURCE_MAP_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(SOURCE_MAP_FILE, dtype=str).fillna("")
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame[columns]


def _write_source_map(frame: pd.DataFrame) -> None:
    SOURCE_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    frame.sort_values("ticker").drop_duplicates("ticker", keep="last").to_csv(SOURCE_MAP_FILE, index=False)


def _metadata_companies() -> dict[str, str]:
    result: dict[str, str] = {}
    if STOCK_METADATA_FILE.exists() and STOCK_METADATA_FILE.stat().st_size:
        frame = pd.read_csv(STOCK_METADATA_FILE, dtype=str).fillna("")
        for row in frame.itertuples(index=False):
            ticker = str(getattr(row, "ticker", "")).strip()
            company = str(getattr(row, "company", "")).strip()
            if ticker and company:
                result[ticker] = company
    return result


def _yahoo_company_name(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).get_info()
        return str(info.get("longName") or info.get("shortName") or "").strip()
    except Exception as exc:
        print(f"VARNING: kunde inte slå upp bolagsnamn för {ticker} via Yahoo: {exc}")
        return ""


def load_universe(only_ticker: str | None = None) -> list[StockIdentity]:
    metadata = _metadata_companies()
    payload = read_json(STOCKS_JSON, default={}) or {}
    tickers = [str(item.get("ticker", "")).strip() for item in payload.get("stocks", []) if item.get("ticker")]
    if not tickers:
        tickers = sorted(metadata)
    if only_ticker:
        normalized = only_ticker.strip().upper()
        tickers = [ticker for ticker in tickers if ticker.upper() == normalized]
        if not tickers:
            tickers = [only_ticker.strip()]
    output: list[StockIdentity] = []
    for ticker in dict.fromkeys(tickers):
        company = metadata.get(ticker, "") or _yahoo_company_name(ticker)
        if not company:
            company = ticker.removesuffix(".ST").replace("-", " ")
        output.append(StockIdentity(ticker=ticker, company=company))
    return output


def resolve_source(
    client: MFNClient,
    stock: StockIdentity,
    source_map: pd.DataFrame,
    *,
    force: bool = False,
) -> tuple[str | None, str | None, pd.DataFrame]:
    existing = source_map.loc[source_map["ticker"] == stock.ticker]
    if not existing.empty and not force:
        row = existing.iloc[-1]
        if row.get("status") == "resolved" and row.get("mfn_slug"):
            return str(row["mfn_slug"]), str(row["mfn_url"]), source_map
        checked = pd.to_datetime(row.get("last_checked"), errors="coerce", utc=True)
        if row.get("status") == "unresolved" and pd.notna(checked):
            if pd.Timestamp.now(tz="UTC") - checked < pd.Timedelta(days=7):
                return None, None, source_map

    resolved_slug: str | None = None
    resolved_url: str | None = None

    def try_candidates(values: Iterable[str]) -> None:
        nonlocal resolved_slug, resolved_url
        for slug in values:
            if resolved_slug:
                return
            valid, url, actual = _verify_company_slug(client, stock.company, slug)
            if valid:
                resolved_slug, resolved_url = slug, url
                return
            if actual and _company_similarity(stock.company, actual) >= 0.40:
                print(f"INFO: svag MFN-träff för {stock.ticker}: {stock.company!r} -> {actual!r} ({url})")

    candidates = _candidate_slugs(stock.company, stock.ticker)
    try_candidates(candidates)
    if not resolved_slug:
        try_candidates(slug for slug in _discover_by_search(client, stock.company) if slug not in candidates)

    row = {
        "ticker": stock.ticker,
        "company": stock.company,
        "mfn_slug": resolved_slug or "",
        "mfn_url": resolved_url or "",
        "status": "resolved" if resolved_slug else "unresolved",
        "last_checked": datetime.now(tz=ZoneInfo("UTC")).isoformat(timespec="seconds"),
    }
    source_map = pd.concat([source_map.loc[source_map["ticker"] != stock.ticker], pd.DataFrame([row])], ignore_index=True)
    return resolved_slug, resolved_url, source_map


def _parse_datetime_from_text(text: str) -> datetime | None:
    match = DATE_RE.search(text or "")
    if not match:
        return None
    clock = match.group("time") or "12:00:00"
    if len(clock) == 5:
        clock += ":00"
    try:
        value = datetime.fromisoformat(f"{match.group('date')}T{clock}")
    except ValueError:
        return None
    return value.replace(tzinfo=STOCKHOLM)


def _nearby_text(anchor: Tag) -> str:
    node: Tag | None = anchor
    chunks: list[str] = []
    for _ in range(5):
        if node is None:
            break
        text = node.get_text(" ", strip=True)
        if text:
            chunks.append(text)
            if DATE_RE.search(text):
                break
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None
    return " ".join(chunks)


def _article_links(soup: BeautifulSoup, *, slug: str, ticker: str, company: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        parsed = urlparse(urljoin(MFN_BASE, str(anchor.get("href", "")).strip()))
        match = ARTICLE_PATH_RE.match(parsed.path)
        if not match or match.group("slug").replace(".iframe", "") != slug:
            continue
        title = anchor.get_text(" ", strip=True)
        if not title or len(title) < 5:
            continue
        clean_path = parsed.path.removesuffix(".iframe")
        canonical = urlunparse(("https", "mfn.se", clean_path, "", "", ""))
        if canonical in seen:
            continue
        published = _parse_datetime_from_text(_nearby_text(anchor))
        if not published:
            continue
        seen.add(canonical)
        output.append(
            {
                "ticker": ticker,
                "company": company,
                "published_at": published.isoformat(timespec="seconds"),
                "title": title,
                "link": canonical,
                "source": "MFN",
            }
        )
    return output


def _pagination_candidates(soup: BeautifulSoup, base_url: str, slug: str) -> list[str]:
    urls: list[str] = []
    triggers = ("visa fler", "show more", "load more", "next", "nästa", "older", "äldre", "cursor", "offset", "page")
    for node in soup.find_all(["a", "button"]):
        text = " ".join(
            [node.get_text(" ", strip=True)]
            + [str(node.get(key, "")) for key in ("class", "id", "rel", "aria-label", "title")]
        ).casefold()
        attrs = [node.get(key) for key in ("href", "data-url", "data-href", "data-next", "hx-get")]
        for value in attrs:
            if not value:
                continue
            url = urljoin(base_url, str(value))
            parsed = urlparse(url)
            if parsed.netloc not in {"mfn.se", "www.mfn.se"}:
                continue
            if not any(token in text or token in url.casefold() for token in triggers):
                continue
            if slug not in url and not any(token in url.casefold() for token in ("cursor", "offset", "page", "load")):
                continue
            if url not in urls:
                urls.append(url)
    return urls


def _year_requests(soup: BeautifulSoup, base_url: str, year: int) -> list[tuple[str, dict[str, str]]]:
    requests_to_try: list[tuple[str, dict[str, str]]] = []
    value = str(year)
    for field in soup.find_all("input"):
        attrs = " ".join(str(field.get(key, "")) for key in ("name", "id", "value", "aria-label"))
        if value not in attrs or not field.get("name"):
            continue
        form = field.find_parent("form")
        params: dict[str, str] = {}
        if form:
            for hidden in form.find_all("input", attrs={"type": "hidden"}):
                if hidden.get("name"):
                    params[str(hidden["name"])] = str(hidden.get("value", ""))
            action = urljoin(base_url, str(form.get("action") or base_url))
        else:
            action = base_url
        params[str(field["name"])] = str(field.get("value") or year)
        requests_to_try.append((action, params))
    for key in ("year", "from_year", "filter_year"):
        requests_to_try.append((base_url, {key: value}))
    unique: list[tuple[str, dict[str, str]]] = []
    seen: set[str] = set()
    for url, params in requests_to_try:
        marker = f"{url}?{urlencode(sorted(params.items()))}"
        if marker not in seen:
            seen.add(marker)
            unique.append((url, params))
    return unique[:8]


def _extract_items_from_response(response: requests.Response, *, slug: str, ticker: str, company: str) -> tuple[list[dict[str, Any]], BeautifulSoup]:
    soup = BeautifulSoup(response.text, "html.parser")
    return _article_links(soup, slug=slug, ticker=ticker, company=company), soup


def fetch_listing_items(
    client: MFNClient,
    stock: StockIdentity,
    slug: str,
    source_url: str,
    *,
    start: date,
    history: bool,
    max_pages: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queue: list[tuple[str, dict[str, str] | None]] = [(source_url, None)]
    iframe_url = source_url.rstrip("/") + ".iframe"
    if iframe_url != source_url:
        queue.append((iframe_url, None))
    visited: set[str] = set()
    items_by_link: dict[str, dict[str, Any]] = {}
    pages = 0
    start_year_seen = False

    while queue and pages < max_pages:
        url, params = queue.pop(0)
        marker = f"{url}?{urlencode(sorted((params or {}).items()))}"
        if marker in visited:
            continue
        visited.add(marker)
        try:
            response = client.get(url, params=params)
        except requests.RequestException as exc:
            print(f"VARNING: MFN-sida kunde inte hämtas för {stock.ticker}: {marker}: {exc}")
            continue
        pages += 1
        found, soup = _extract_items_from_response(response, slug=slug, ticker=stock.ticker, company=stock.company)
        if any(str(item.get("published_at", "")).startswith(str(start.year)) for item in found):
            start_year_seen = True
        for item in found:
            items_by_link[item["link"]] = item
        for next_url in _pagination_candidates(soup, response.url, slug):
            queue.append((next_url, None))

        if history and pages <= 2:
            for year in range(start.year, datetime.now(STOCKHOLM).year + 1):
                for year_url, year_params in _year_requests(soup, source_url, year):
                    queue.append((year_url, year_params))

    dates = [pd.to_datetime(item["published_at"], errors="coerce") for item in items_by_link.values()]
    valid_dates = [stamp for stamp in dates if pd.notna(stamp)]
    oldest = min(valid_dates).date().isoformat() if valid_dates else None
    newest = max(valid_dates).date().isoformat() if valid_dates else None
    reached_start = bool(oldest and date.fromisoformat(oldest) <= start)
    complete = bool(start_year_seen or reached_start)
    coverage_method = "year_filter_or_listing" if start_year_seen else ("pagination_to_start" if reached_start else "partial")
    return sorted(items_by_link.values(), key=lambda item: item["published_at"], reverse=True), {
        "pages_fetched": pages,
        "oldest_seen": oldest,
        "newest_seen": newest,
        "history_complete": complete if history else None,
        "coverage_method": coverage_method if history else "latest_listing",
    }


def _contains(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def classify_relevance(title: str, summary: str = "") -> Relevance:
    text = unicodedata.normalize("NFKC", f"{title} {summary}").casefold()
    text = re.sub(r"[^0-9a-zåäöéü&/+.-]+", " ", text).strip()

    if _contains(REPORT_PATTERNS, text):
        return Relevance("drop", "report", "represented_as_E")

    for topic, patterns in HIGH_MATERIAL_PATTERNS:
        if _contains(patterns, text):
            return Relevance("keep", topic, f"material:{topic}")

    if _contains(DIVIDEND_ROUTINE_PATTERNS, text):
        return Relevance("drop", "dividend", "represented_as_D")
    if _contains(ROUTINE_PATTERNS, text):
        return Relevance("drop", "routine", "routine_market_notice")

    for topic, patterns in COMMERCIAL_PATTERNS:
        if _contains(patterns, text):
            if _contains(MATERIALITY_QUALIFIERS, text):
                return Relevance("keep", topic, f"material_commercial:{topic}")
            return Relevance("review", topic, f"commercial_needs_materiality_review:{topic}")

    return Relevance("review", "other", "no_high_confidence_rule")


def _summary_from_soup(soup: BeautifulSoup) -> str:
    text = ""
    for selector in ("[itemprop='articleBody']", "article", ".article-body", ".press-release", ".release-body", "main"):
        node = soup.select_one(selector)
        if node:
            candidate = node.get_text(" ", strip=True)
            if len(candidate) > len(text):
                text = candidate
        if len(text) >= 300:
            break
    text = re.sub(r"\s+", " ", text).strip()
    for marker in ("MFN - en produkt från", "All ägardata du vill ha finns i Holdings", "Intresserad av bolagets nyckeltal"):
        text = text.split(marker, 1)[0].strip()
    return text[:MAX_SUMMARY_CHARS]


def _is_regulatory(soup: BeautifulSoup, text: str) -> bool:
    tags = " ".join(
        str(meta.get("content", "")) for meta in soup.find_all("meta")
        if str(meta.get("name", "")).lower() in {"keywords", "category"}
        or str(meta.get("property", "")).lower().endswith("tag")
    )
    haystack = f"{tags} {text}".casefold()
    return any(marker in haystack for marker in REGULATORY_MARKERS)


def enrich_item(client: MFNClient, item: dict[str, Any], initial: Relevance) -> tuple[dict[str, Any], Relevance]:
    summary = ""
    regulatory = False
    relevance = initial
    if initial.status in {"keep", "review"}:
        try:
            response = client.get(item["link"])
            soup = BeautifulSoup(response.text, "html.parser")
            summary = _summary_from_soup(soup)
            regulatory = _is_regulatory(soup, summary)
            if initial.status == "review" and summary:
                relevance = classify_relevance(item["title"], summary)
        except requests.RequestException as exc:
            print(f"VARNING: kunde inte läsa MFN-artikel {item['link']}: {exc}")
    result = dict(item)
    result["summary"] = summary
    result["is_regulatory"] = regulatory
    result["categories"] = ["news", relevance.topic]
    result["relevance"] = relevance.status
    result["relevance_reason"] = relevance.reason
    result["review_status"] = "unreviewed"
    result["classification"] = "unreviewed"
    result["lock_action"] = "none"
    result["review_note"] = ""
    result["event_type"] = "news"
    result["event_id"] = stable_event_id(
        str(result["ticker"]), str(result["link"]), str(result["published_at"]), str(result["title"])
    )
    return result, relevance


def _language(title: str) -> str:
    normalized = _normalize_text(title)
    tokens = set(normalized.split())
    if any(char in title.casefold() for char in "åäö") or len(tokens & SWEDISH_HINTS) > len(tokens & ENGLISH_HINTS):
        return "sv"
    return "en"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact: dict[tuple[str, str], dict[str, Any]] = {}
    for item in sorted(items, key=lambda row: row.get("published_at", ""), reverse=True):
        key = (_normalize_text(item.get("title", "")), str(item.get("published_at", ""))[:16])
        exact.setdefault(key, item)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in exact.values():
        minute = str(item.get("published_at", ""))[:16]
        topic = str(item.get("relevance_reason", "")).split(":")[-1]
        grouped.setdefault((minute, topic), []).append(item)

    output: list[dict[str, Any]] = []
    for group in grouped.values():
        if len(group) == 1:
            output.extend(group)
            continue
        swedish = [item for item in group if _language(str(item.get("title", ""))) == "sv"]
        chosen = swedish[0] if swedish else group[0]
        output.append(chosen)
        for item in group:
            if item is chosen:
                continue
            ratio = SequenceMatcher(None, _normalize_text(chosen.get("title", "")), _normalize_text(item.get("title", ""))).ratio()
            if ratio < 0.25 and _language(str(item.get("title", ""))) == _language(str(chosen.get("title", ""))):
                output.append(item)
    return sorted(output, key=lambda row: row.get("published_at", ""), reverse=True)


def _load_existing_news(ticker: str) -> list[dict[str, Any]]:
    payload = read_json(NEWS_ROOT / f"{ticker}.json", default=[]) or []
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    return [dict(item) for item in payload if isinstance(item, dict)]


def _merge_items(existing: list[dict[str, Any]], new_items: list[dict[str, Any]], *, start: date) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_key: dict[tuple[str, str], str] = {}
    for item in [*existing, *new_items]:
        published = pd.to_datetime(item.get("published_at"), errors="coerce", utc=True)
        if pd.isna(published) or published.date() < start:
            continue
        event_id = str(item.get("event_id") or stable_event_id(
            str(item.get("ticker", "")), str(item.get("link", "")), str(item.get("published_at", "")), str(item.get("title", ""))
        ))
        item = dict(item)
        item["event_id"] = event_id
        key = (_normalize_text(item.get("title", "")), str(item.get("published_at", ""))[:16])
        prior_id = by_key.get(key)
        if prior_id and prior_id in by_id:
            if len(str(item.get("summary", ""))) > len(str(by_id[prior_id].get("summary", ""))):
                by_id[prior_id] = item
            continue
        by_id[event_id] = item
        by_key[key] = event_id
    return _dedupe(list(by_id.values()))


def _load_review_queue() -> list[dict[str, Any]]:
    payload = read_json(REVIEW_QUEUE_FILE, default={}) or {}
    items = payload.get("items", []) if isinstance(payload, dict) else payload
    return [dict(item) for item in items if isinstance(item, dict)]


def _write_review_queue(items: list[dict[str, Any]], *, start: date) -> None:
    write_json_atomic(
        REVIEW_QUEUE_FILE,
        {
            "generated_at": datetime.now(STOCKHOLM).isoformat(timespec="seconds"),
            "description": "Osäkra MFN-poster som inte visas automatiskt som N.",
            "items": _merge_items([], items, start=start),
        },
        pretty=True,
    )


def _daily_cutoff(existing: list[dict[str, Any]], review_queue: list[dict[str, Any]], ticker: str, start: date) -> date:
    dates: list[date] = []
    for item in [*existing, *(row for row in review_queue if row.get("ticker") == ticker)]:
        stamp = pd.to_datetime(item.get("published_at"), errors="coerce", utc=True)
        if pd.notna(stamp):
            dates.append(stamp.date())
    if not dates:
        return max(start, datetime.now(STOCKHOLM).date() - timedelta(days=21))
    return max(start, max(dates) - timedelta(days=7))


def publish_news_events() -> dict[str, Any]:
    """Replace only N events in docs/data/events.json and preserve current E/D events."""
    current = read_json(EVENTS_JSON, default={}) or {}
    existing_events = current.get("events", []) if isinstance(current, dict) else []
    non_news = [dict(item) for item in existing_events if str(item.get("event_type", "")) != "news"]
    reviews = load_reviews()
    news_events: list[dict[str, Any]] = []

    if NEWS_ROOT.exists():
        for path in sorted(NEWS_ROOT.glob("*.json")):
            payload = read_json(path, default=[]) or []
            items = payload.get("items", []) if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                continue
            ticker = path.stem
            clean_items = [dict(row) for row in items if isinstance(row, dict)]
            for item in enrich_news(ticker, clean_items, reviews):
                entry = dict(item)
                entry["event_type"] = "news"
                categories = list(entry.get("categories") or [])
                if "news" not in categories:
                    categories.insert(0, "news")
                entry["categories"] = categories
                action = str(entry.get("lock_action", "none"))
                unreviewed_regulatory = entry.get("review_status") == "unreviewed" and bool(entry.get("is_regulatory"))
                entry["locking"] = bool(unreviewed_regulatory or action == "lock_until_verified_report")
                news_events.append(entry)

    combined = non_news + news_events
    combined.sort(key=lambda item: str(item.get("published_at", "")), reverse=True)
    output = dict(current) if isinstance(current, dict) else {}
    output["generated_at"] = datetime.now(STOCKHOLM).isoformat(timespec="seconds")
    output.setdefault("is_demo", False)
    output["events"] = combined
    write_json_atomic(EVENTS_JSON, output)
    return {"news_events": len(news_events), "preserved_non_news_events": len(non_news)}


def update_news(
    *,
    start: date = DEFAULT_START,
    history: bool = False,
    only_ticker: str | None = None,
    max_pages: int | None = None,
    delay: float = REQUEST_DELAY_SECONDS,
) -> dict[str, Any]:
    NEWS_ROOT.mkdir(parents=True, exist_ok=True)
    NEWS_META_ROOT.mkdir(parents=True, exist_ok=True)
    client = MFNClient(delay=delay)
    source_map = _load_source_map()
    review_queue = _load_review_queue()
    review_by_id = {str(item.get("event_id")): item for item in review_queue if item.get("event_id")}
    statuses: dict[str, Any] = {}
    universe = load_universe(only_ticker)
    pages_limit = max_pages or (40 if history else 4)

    for index, stock in enumerate(universe, start=1):
        print(f"[{index}/{len(universe)}] Nyheter {stock.ticker} · {stock.company}")
        slug, source_url, source_map = resolve_source(client, stock, source_map, force=history)
        if not slug or not source_url:
            statuses[stock.ticker] = {
                "company": stock.company,
                "status": "source_unresolved",
                "history_complete": False if history else None,
            }
            continue

        existing = _load_existing_news(stock.ticker)
        cutoff = start if history else _daily_cutoff(existing, review_queue, stock.ticker, start)
        listing, coverage = fetch_listing_items(
            client, stock, slug, source_url, start=start if history else cutoff, history=history, max_pages=pages_limit
        )
        candidates = [
            item for item in listing
            if pd.to_datetime(item.get("published_at"), errors="coerce", utc=True).date() >= cutoff
        ]
        kept: list[dict[str, Any]] = []
        reviewed: list[dict[str, Any]] = []
        dropped = 0
        existing_keys = {
            (_normalize_text(item.get("title", "")), str(item.get("published_at", ""))[:16])
            for item in existing
        }
        review_keys = {
            (_normalize_text(item.get("title", "")), str(item.get("published_at", ""))[:16])
            for item in review_queue if item.get("ticker") == stock.ticker
        }

        for item in candidates:
            key = (_normalize_text(item.get("title", "")), str(item.get("published_at", ""))[:16])
            if not history and (key in existing_keys or key in review_keys):
                continue
            initial = classify_relevance(str(item.get("title", "")))
            if initial.status == "drop":
                dropped += 1
                continue
            enriched, relevance = enrich_item(client, item, initial)
            if relevance.status == "keep":
                kept.append(enriched)
            elif relevance.status == "review":
                reviewed.append(enriched)
            else:
                dropped += 1

        merged = _merge_items(existing, kept, start=start)
        write_json_atomic(
            NEWS_ROOT / f"{stock.ticker}.json",
            {
                "generated_at": datetime.now(STOCKHOLM).isoformat(timespec="seconds"),
                "source": "MFN",
                "source_url": source_url,
                "items": merged,
            },
            pretty=True,
        )
        for item in reviewed:
            review_by_id[str(item["event_id"])] = item

        statuses[stock.ticker] = {
            "company": stock.company,
            "status": "ok",
            "source_url": source_url,
            "cutoff": cutoff.isoformat(),
            "listing_candidates": len(candidates),
            "new_kept": len(kept),
            "new_review": len(reviewed),
            "dropped": dropped,
            "stored_keep": len(merged),
            **coverage,
        }

    _write_source_map(source_map)
    all_review = list(review_by_id.values())
    _write_review_queue(all_review, start=start)
    payload = {
        "generated_at": datetime.now(STOCKHOLM).isoformat(timespec="seconds"),
        "source": "MFN public company pages",
        "history_start": start.isoformat(),
        "history_mode": history,
        "stocks": statuses,
        "summary": {
            "stocks_total": len(universe),
            "sources_resolved": sum(item.get("status") == "ok" for item in statuses.values()),
            "sources_unresolved": sum(item.get("status") == "source_unresolved" for item in statuses.values()),
            "history_complete": sum(item.get("history_complete") is True for item in statuses.values()),
            "review_queue": len(all_review),
        },
    }
    write_json_atomic(STATUS_FILE, payload, pretty=True)
    published = publish_news_events()
    payload["published"] = published
    write_json_atomic(STATUS_FILE, payload, pretty=True)
    print(
        "Nyhetsuppdatering klar: "
        f"{payload['summary']['sources_resolved']} källor lösta, "
        f"{payload['summary']['sources_unresolved']} olösta, "
        f"{payload['summary']['review_queue']} poster i review-kö, "
        f"{published['news_events']} publicerade N-händelser."
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Hämta och relevansfiltrera bolagsmeddelanden från MFN.")
    parser.add_argument("--history", action="store_true", help="Backfill historik och försök använda MFN:s årsfilter/paginering.")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START, help="Tidigaste datum, YYYY-MM-DD (default 2024-01-01).")
    parser.add_argument("--ticker", help="Kör endast en Yahoo-ticker, t.ex. ERIC-B.ST.")
    parser.add_argument("--max-pages", type=int, default=None, help="Max MFN-svar per aktie.")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS, help="Minsta paus mellan MFN-anrop i sekunder.")
    args = parser.parse_args()
    update_news(
        start=args.start,
        history=args.history,
        only_ticker=args.ticker,
        max_pages=args.max_pages,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
