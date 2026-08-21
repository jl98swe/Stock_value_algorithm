"""Strict, low-noise relevance policy for MFN company news.

``src.news`` owns MFN discovery, fetching and publication. This module owns the
production relevance policy and guarantees mutually exclusive storage:

- ``keep``   -> ``data/raw/news/<ticker>.json`` -> published as N
- ``review`` -> ``data/news/review_queue.json`` only
- ``drop``   -> stored nowhere

Production workflows must run this module, not ``src.news`` directly.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable

from . import news as base

_BASE_CLASSIFIER = base.classify_relevance

# Reports already have an E representation and must never be duplicated as N.
EXTRA_REPORT_TITLE_PATTERNS = (
    r"\breports? (?:the )?(?:first|second|third|fourth) quarter\b",
    r"\breports? .*\b(?:quarter|full[- ]year|year[- ]end) results?\b",
    r"\b(?:first|second|third|fourth) quarter(?: and full[- ]year)? results?\b",
    r"\bfull[- ]year results?\b",
    r"\bpublishes? .*\b(?:quarterly|interim|full[- ]year|year[- ]end) (?:report|results?)\b",
    r"\b(?:q[1-4]|fy)\s*20\d{2}\s+results?\b",
    r"\bresultat för (?:första|andra|tredje|fjärde) kvartalet\b",
    r"\brapporterar (?:det )?(?:första|andra|tredje|fjärde) kvartal(?:et)?(?:\s+20\d{2})?\b",
    r"\brapporterar .*?\b(?:kvartal(?:et)?|helår(?:et)?|resultat(?:et)?)\b",
)

BUYBACK_TITLE_PATTERNS = (
    r"\baktieåterköp\b",
    r"\båterköp(?:sprogram)?\b.*\baktier\b",
    r"\båterköper\b.*\baktier\b",
    r"\bköp av egna aktier\b",
    r"\bshare buy[- ]?backs?\b",
    r"\bbuy[- ]?back\b.*\bshares?\b",
    r"\bshare repurchase(?:s| program| programme)?\b",
    r"\brepurchase(?:s|d)?\b.*\bshares?\b",
    r"\brepurchase program(?:me)?\b",
)

SHARE_ADMIN_TITLE_PATTERNS = (
    r"\böverlåtelsebemyndigande\b",
    r"\banvänder .*överlåtelsebemyndigande\b",
    r"\böverlåtelse av egna aktier\b",
    r"\bbemyndigande .*överlåta (?:egna )?aktier\b",
    r"\btransfer authori[sz]ation\b",
    r"\bauthori[sz]ation to transfer (?:own |treasury )?shares?\b",
    r"\bmandate to transfer shares?\b",
    r"\butili[sz]e .*mandate to transfer shares?\b",
    r"\buses? .*authori[sz]ation .*transfer .*shares?\b",
    r"\btransfer of (?:own|treasury) shares?\b",
    r"\bdisposal of treasury shares?\b",
)

OFFICE_TITLE_PATTERNS = (
    r"\bopens? (?:a )?(?:new )?office\b",
    r"\bnew office\b",
    r"\bmoves? .*\boffice\b",
    r"\brelocat(?:e|es|ed|ing|ion).*\boffice\b",
    r"\bopens? (?:a )?(?:new )?(?:head office|headquarters)\b",
    r"\bnew (?:head office|headquarters)\b",
    r"\b(?:moves?|relocat(?:e|es|ed|ing|ion)).*\b(?:head office|headquarters)\b",
    r"\brelocat(?:e|es|ed|ing|ion).*\boperations\b",
    r"\bmoves? .*\boperations\b",
    r"\böppnar (?:ett )?(?:nytt )?kontor\b",
    r"\bnytt kontor\b",
    r"\bflyttar .*\bkontor\b",
    r"\bnytt huvudkontor\b",
    r"\bflyttar .*\bhuvudkontor\b",
    r"\bflyttar .*\bverksamhet\b",
)

# Only the largest leadership roles are automatically relevant.
MAJOR_LEADERSHIP_TITLE_PATTERNS = (
    r"\bnew ceo\b",
    r"\bappoints? .*\bceo\b",
    r"\bappointed (?:as )?(?:new )?ceo\b",
    r"\bceo .*\b(?:resign|steps? down|leave|depart)\b",
    r"\bchief executive .*\b(?:appoint|resign|steps? down|leave|depart)\b",
    r"\bny vd\b",
    r"\butser .*\bvd\b",
    r"\butsedd till (?:ny )?vd\b",
    r"\bvd .*\b(?:avgår|slutar|lämnar)\b",
    r"\bvd-byte\b",
    r"\bnew cfo\b",
    r"\bappoints? .*\bcfo\b",
    r"\bappointed (?:as )?(?:new )?cfo\b",
    r"\bcfo .*\b(?:resign|steps? down|leave|depart)\b",
    r"\bny finansdirektör\b",
    r"\butser .*\bfinansdirektör\b",
    r"\butsedd till (?:ny )?finansdirektör\b",
    r"\bfinansdirektör .*\b(?:avgår|slutar|lämnar)\b",
    r"\bnew (?:board )?(?:chair|chairman|chairwoman)\b",
    r"\bappoints? .*\b(?:chair|chairman|chairwoman)\b",
    r"\bny styrelseordförande\b",
    r"\butser .*\bstyrelseordförande\b",
)

INTERNAL_LEADERSHIP_TITLE_PATTERNS = (
    r"\bförändring(?:ar)? i (?:koncernledningen|koncernledning)\b",
    r"\bförändring(?:ar)? i .*\bledningsgrupp\b",
    r"\bchanges? (?:to|in) (?:the )?(?:group executive team|executive team|group management|management team)\b",
    r"\bmanagement changes?\b",
    r"\bappoints? (?:a |new )?head of\b",
    r"\bnew head of\b",
    r"\bhead of (?:business area|business unit|division|region|market area|segment|function)\b",
    r"\bpresident of (?:business area|business unit|division|region|market area|segment)\b",
    r"\bcountry manager\b",
    r"\butser .*\bchef för\b",
    r"\butsedd till .*\bchef för\b",
    r"\bny chef för\b",
    r"\bchef för affärsområd\w*\b",
    r"\baffärsområdeschef\b",
    r"\bdivisionschef\b",
    r"\bregionchef\b",
    r"\bsegmentchef\b",
    r"\bmarknadsområdeschef\b",
)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^0-9a-zåäöéü&/+.-]+", " ", text).strip()


def _contains(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def _hard_title_decision(title: str) -> base.Relevance | None:
    """Return a final decision only for unambiguous title-level cases."""
    text = _normalize(title)

    if _contains(EXTRA_REPORT_TITLE_PATTERNS, text):
        return base.Relevance("drop", "report", "represented_as_E")

    # Protect a true CEO/CFO/chair change from broad management exclusions.
    if _contains(MAJOR_LEADERSHIP_TITLE_PATTERNS, text):
        return None

    if _contains(BUYBACK_TITLE_PATTERNS, text):
        return base.Relevance("drop", "buyback", "user_excluded:share_buyback")
    if _contains(SHARE_ADMIN_TITLE_PATTERNS, text):
        return base.Relevance("drop", "share_admin", "user_excluded:share_administration")
    if _contains(OFFICE_TITLE_PATTERNS, text):
        return base.Relevance("drop", "office", "user_excluded:office_change")
    if _contains(INTERNAL_LEADERSHIP_TITLE_PATTERNS, text):
        return base.Relevance("drop", "leadership_internal", "user_excluded:non_major_leadership")
    return None


def classify_relevance(title: str, summary: str = "") -> base.Relevance:
    """Canonical final decision for one complete press release."""
    hard = _hard_title_decision(title)
    if hard is not None:
        return hard

    if _contains(MAJOR_LEADERSHIP_TITLE_PATTERNS, _normalize(title)):
        return base.Relevance("keep", "leadership_major", "material:leadership_major")

    result = _BASE_CLASSIFIER(title, summary)
    if result.topic == "leadership":
        return base.Relevance("drop", "leadership_internal", "user_excluded:non_major_leadership")
    return result


def _preclassify_title(title: str, summary: str = "") -> base.Relevance:
    """Cheap prefilter used by src.news before it requests the article body.

    This is not a second final classification. It returns a final result only
    for hard title-level drops; everything else is marked pending so the article
    can be fetched and classified once with full evidence.
    """
    hard = _hard_title_decision(title)
    if hard is not None:
        return hard
    return base.Relevance("review", "pending", "pending_full_classification")


def _decorate(
    item: dict[str, Any],
    relevance: base.Relevance,
    *,
    summary: str | None = None,
    is_regulatory: bool | None = None,
) -> dict[str, Any]:
    entry = dict(item)
    if summary is not None:
        entry["summary"] = summary
    entry.setdefault("summary", "")
    if is_regulatory is not None:
        entry["is_regulatory"] = bool(is_regulatory)
    entry.setdefault("is_regulatory", False)
    entry["categories"] = ["news", relevance.topic]
    entry["relevance"] = relevance.status
    entry["relevance_reason"] = relevance.reason
    entry.setdefault("review_status", "unreviewed")
    entry.setdefault("classification", "unreviewed")
    entry.setdefault("lock_action", "none")
    entry.setdefault("review_note", "")
    entry["event_type"] = "news"
    entry["event_id"] = str(
        entry.get("event_id")
        or base.stable_event_id(
            str(entry.get("ticker", "")),
            str(entry.get("link", "")),
            str(entry.get("published_at", "")),
            str(entry.get("title", "")),
        )
    )
    return entry


def _enrich_and_classify_once(
    client: base.MFNClient,
    item: dict[str, Any],
    initial: base.Relevance,
) -> tuple[dict[str, Any], base.Relevance]:
    """Fetch summary, then make exactly one final relevance decision."""
    summary = ""
    regulatory = False
    try:
        response = client.get(str(item["link"]))
        soup = base.BeautifulSoup(response.text, "html.parser")
        summary = base._summary_from_soup(soup)
        regulatory = base._is_regulatory(soup, summary)
    except base.requests.RequestException as exc:
        print(f"VARNING: kunde inte läsa MFN-artikel {item.get('link')}: {exc}")

    relevance = classify_relevance(str(item.get("title", "")), summary)
    return _decorate(item, relevance, summary=summary, is_regulatory=regulatory), relevance


def _item_key(item: dict[str, Any]) -> str:
    event_id = str(item.get("event_id", "")).strip()
    if event_id:
        return event_id
    return base.stable_event_id(
        str(item.get("ticker", "")),
        str(item.get("link", "")),
        str(item.get("published_at", "")),
        str(item.get("title", "")),
    )


def _dedupe_input(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        key = _item_key(item)
        previous = by_id.get(key)
        if previous is None or len(str(item.get("summary", ""))) > len(str(previous.get("summary", ""))):
            by_id[key] = item
    return list(by_id.values())


def _write_partitioned_state(
    keep_items: list[dict[str, Any]],
    review_items: list[dict[str, Any]],
    existing_payloads: dict[str, dict[str, Any]],
) -> None:
    keep_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for item in keep_items:
        ticker = str(item.get("ticker", ""))
        if ticker:
            keep_by_ticker.setdefault(ticker, []).append(item)

    all_tickers = set(existing_payloads) | set(keep_by_ticker)
    for ticker in sorted(all_tickers):
        payload = dict(existing_payloads.get(ticker, {}))
        payload["generated_at"] = datetime.now(base.STOCKHOLM).isoformat(timespec="seconds")
        payload.setdefault("source", "MFN")
        payload["items"] = base._merge_items([], keep_by_ticker.get(ticker, []), start=base.DEFAULT_START)
        base.write_json_atomic(base.NEWS_ROOT / f"{ticker}.json", payload, pretty=True)

    # Hard invariant: only review decisions may exist in review_queue.json.
    assert all(item.get("relevance") == "review" for item in review_items)
    base._write_review_queue(review_items, start=base.DEFAULT_START)


def validate_storage_partition() -> dict[str, int]:
    keep_count = 0
    if base.NEWS_ROOT.exists():
        for path in sorted(base.NEWS_ROOT.glob("*.json")):
            payload = base.read_json(path, default={}) or {}
            items = payload.get("items", []) if isinstance(payload, dict) else payload
            for item in items if isinstance(items, list) else []:
                if str(item.get("relevance", "")) != "keep":
                    raise RuntimeError(
                        f"Ogiltig rånyhet i {path}: {item.get('title')} [{item.get('relevance')}]"
                    )
                keep_count += 1

    queue = base._load_review_queue()
    for item in queue:
        if str(item.get("relevance", "")) != "review":
            raise RuntimeError(
                f"Ogiltig review-köpost: {item.get('title')} [{item.get('relevance')}]"
            )
    return {"keep": keep_count, "review": len(queue)}


def clean_existing_news() -> dict[str, int]:
    """Rebuild persisted news into mutually exclusive keep/review/drop sets."""
    base.NEWS_ROOT.mkdir(parents=True, exist_ok=True)
    base.NEWS_META_ROOT.mkdir(parents=True, exist_ok=True)

    existing_payloads: dict[str, dict[str, Any]] = {}
    all_items: list[dict[str, Any]] = []

    for path in sorted(base.NEWS_ROOT.glob("*.json")):
        payload = base.read_json(path, default={}) or {}
        if isinstance(payload, dict):
            existing_payloads[path.stem] = dict(payload)
            items = payload.get("items", [])
        else:
            existing_payloads[path.stem] = {"source": "MFN"}
            items = payload
        if isinstance(items, list):
            all_items.extend(dict(item) for item in items if isinstance(item, dict))

    # Review and raw news are deliberately pooled, deduplicated and classified
    # once again. This fixes historical leakage between the two stores.
    all_items.extend(base._load_review_queue())

    keep_items: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    dropped = 0

    for item in _dedupe_input(all_items):
        relevance = classify_relevance(
            str(item.get("title", "")),
            str(item.get("summary", "")),
        )
        classified = _decorate(item, relevance)
        if relevance.status == "keep":
            keep_items.append(classified)
        elif relevance.status == "review":
            review_items.append(classified)
        else:
            dropped += 1

    _write_partitioned_state(keep_items, review_items, existing_payloads)
    base.publish_news_events()
    counts = validate_storage_partition()
    return {"kept": counts["keep"], "review": counts["review"], "dropped": dropped}


def main() -> None:
    # First fix any data produced by earlier versions of the policy.
    stats = clean_existing_news()
    if stats["dropped"]:
        print(
            "Rensade tidigare nyhetsurval: "
            f"{stats['dropped']} borttagna; "
            f"{stats['kept']} keep och {stats['review']} review återstår."
        )

    # src.news first asks for a cheap title decision and then calls enrich_item.
    # Non-hard-drop items are only finally classified inside our replacement
    # enrich_item after the summary has been fetched.
    base.classify_relevance = _preclassify_title
    base.enrich_item = _enrich_and_classify_once
    base.main()

    # Fail loudly if future changes ever leak keep/drop items into review or raw.
    validate_storage_partition()


if __name__ == "__main__":
    main()
