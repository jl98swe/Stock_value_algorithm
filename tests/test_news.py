import json

from bs4 import BeautifulSoup

from src import news as base_news
from src.news import _article_links, _dedupe
from src.news_curated import classify_relevance, clean_existing_news


def test_relevance_keeps_material_events():
    assert classify_relevance("Bolaget vinstvarnar för Q3").status == "keep"
    assert classify_relevance("Ericsson appoints new CEO").status == "keep"
    assert classify_relevance("Ericsson utser ny VD").status == "keep"
    assert classify_relevance("Company appoints new CFO").status == "keep"
    assert classify_relevance("Company receives significant order worth SEK 250 million").status == "keep"
    assert classify_relevance("Bolaget ställer in utdelning").status == "keep"


def test_relevance_drops_report_dividend_and_routine_noise():
    assert classify_relevance("Delårsrapport januari-mars 2026").topic == "report"
    assert classify_relevance("Interim report Q2 2026 with revised guidance").topic == "report"
    assert classify_relevance("Ericsson reports fourth quarter and full-year results 2025").topic == "report"
    assert classify_relevance("Ericsson rapporterar andra kvartalet 2026").topic == "report"
    assert classify_relevance("X-dag ordinarie utdelning 2,50 SEK").topic == "dividend"
    assert classify_relevance("Kallelse till årsstämma").status == "drop"


def test_relevance_drops_all_share_buyback_noise():
    cases = [
        "Ericsson repurchases own shares",
        "Share buyback program in Ericsson",
        "Transactions made under the share buyback program",
        "Återköp av egna aktier i Ericsson",
        "Aktieåterköp i Ericsson under perioden 3 augusti - 7 augusti 2026",
        "Rättelse: Aktieåterköp i Ericsson under perioden 20 april - 24 april 2026",
    ]
    for title in cases:
        result = classify_relevance(title)
        assert result.status == "drop", title
        assert result.topic == "buyback", title


def test_relevance_drops_share_transfer_administration():
    cases = [
        "Ericsson använder överlåtelsebemyndigande",
        "Ericsson uses authorization to transfer own shares",
        "Transfer of treasury shares in Ericsson",
        "Ericsson to utilize mandate to transfer shares",
    ]
    for title in cases:
        result = classify_relevance(title)
        assert result.status == "drop", title
        assert result.topic == "share_admin", title


def test_relevance_drops_non_major_management_changes():
    cases = [
        "Ericsson announces changes to Group Executive Team",
        "Ericsson meddelar förändring i koncernledningen",
        "Ericsson appoints new Head of Business Area Enterprise Wireless Solutions",
        "Ericsson utser ny chef för affärsområdet Enterprise Wireless Solutions",
        "Company appoints new Head of Region Europe",
    ]
    for title in cases:
        result = classify_relevance(title)
        assert result.status == "drop", title
        assert result.topic == "leadership_internal", title


def test_relevance_drops_office_changes():
    cases = [
        "Ericsson opens new office in Stockholm",
        "Ericsson moves to a new office",
        "Ericsson flyttar till nytt kontor",
        "Company relocates headquarters",
        "Ericsson to relocate Stockholm operations to Hagastaden",
    ]
    for title in cases:
        result = classify_relevance(title)
        assert result.status == "drop", title
        assert result.topic == "office", title


def test_real_ericsson_ceo_change_is_kept():
    result = classify_relevance(
        "Ericsson: Per Narvinger utsedd till vd och koncernchef då Börje Ekholm slutar"
    )
    assert result.status == "keep"
    assert result.topic == "leadership_major"


def test_generic_management_summary_does_not_promote_to_news():
    result = classify_relevance(
        "Ericsson announces changes to Group Executive Team",
        "The changes were announced by the CEO and include several appointments.",
    )
    assert result.status == "drop"
    assert result.topic == "leadership_internal"


def test_generic_contract_is_review_not_news():
    result = classify_relevance("Company signs agreement with customer")
    assert result.status == "review"
    assert result.topic == "contract"


def test_clean_existing_news_moves_keep_out_of_review_and_removes_drop(tmp_path, monkeypatch):
    news_root = tmp_path / "raw" / "news"
    news_meta_root = tmp_path / "news"
    review_file = news_meta_root / "review_queue.json"
    news_root.mkdir(parents=True)
    news_meta_root.mkdir(parents=True)

    common = {
        "ticker": "ERIC-B.ST",
        "company": "Ericsson B",
        "source": "MFN",
        "summary": "",
        "is_regulatory": False,
        "review_status": "unreviewed",
        "classification": "unreviewed",
        "lock_action": "none",
        "review_note": "",
        "event_type": "news",
    }
    review_file.write_text(
        json.dumps(
            {
                "items": [
                    {
                        **common,
                        "event_id": "buyback",
                        "published_at": "2026-08-10T08:30:00+02:00",
                        "title": "Aktieåterköp i Ericsson under perioden 3 augusti - 7 augusti 2026",
                        "link": "https://mfn.se/buyback",
                        "relevance": "review",
                    },
                    {
                        **common,
                        "event_id": "ceo",
                        "published_at": "2026-06-16T12:20:00+02:00",
                        "title": "Ericsson: Per Narvinger utsedd till vd och koncernchef då Börje Ekholm slutar",
                        "link": "https://mfn.se/ceo",
                        "relevance": "keep",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(base_news, "NEWS_ROOT", news_root)
    monkeypatch.setattr(base_news, "NEWS_META_ROOT", news_meta_root)
    monkeypatch.setattr(base_news, "REVIEW_QUEUE_FILE", review_file)
    monkeypatch.setattr(base_news, "publish_news_events", lambda: {"news_events": 1})

    result = clean_existing_news()

    queue = json.loads(review_file.read_text(encoding="utf-8"))["items"]
    raw = json.loads((news_root / "ERIC-B.ST.json").read_text(encoding="utf-8"))["items"]
    assert result == {"kept": 1, "review": 0, "dropped": 1}
    assert queue == []
    assert len(raw) == 1
    assert raw[0]["event_id"] == "ceo"
    assert raw[0]["relevance"] == "keep"


def test_listing_parser_extracts_mfn_article():
    html = """
    <html><body>
      <div class="release-row">
        <time>2024-05-03 07:30:00</time>
        <a href="/a/acme/acme-wins-significant-contract">Acme wins significant contract</a>
      </div>
    </body></html>
    """
    items = _article_links(BeautifulSoup(html, "html.parser"), slug="acme", ticker="ACME.ST", company="Acme")
    assert len(items) == 1
    assert items[0]["published_at"] == "2024-05-03T07:30:00+02:00"
    assert items[0]["link"] == "https://mfn.se/a/acme/acme-wins-significant-contract"


def test_language_twins_are_deduplicated():
    base = {
        "ticker": "ACME.ST",
        "published_at": "2026-05-05T08:00:00+02:00",
        "relevance_reason": "material:acquisition",
    }
    items = [
        {**base, "event_id": "sv", "title": "Acme förvärvar Bolag AB"},
        {**base, "event_id": "en", "title": "Acme acquires Company Ltd"},
    ]
    result = _dedupe(items)
    assert len(result) == 1
    assert result[0]["event_id"] == "sv"
