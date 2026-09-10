from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


PAGES = {
    "index.html": "./index.html",
    "positions.html": "./positions.html",
    "signals.html": "./signals.html",
    "review.html": "./review.html",
}

EXPECTED_LINKS = [
    ("./index.html", "Startsida"),
    ("./positions.html", "Aktiva positioner"),
    ("./signals.html", "Kommande signaler"),
    ("./review.html", "Granska nyheter och data"),
]


class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_navigation = False
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav" and attrs.get("aria-label") == "Huvudnavigation":
            self.in_navigation = True
        elif self.in_navigation and tag == "a":
            self.links.append(
                {
                    "href": urlsplit(attrs.get("href", "")).path,
                    "label": "",
                    "current": attrs.get("aria-current"),
                }
            )

    def handle_data(self, data):
        if self.in_navigation and self.links:
            self.links[-1]["label"] += data.strip()

    def handle_endtag(self, tag):
        if self.in_navigation and tag == "nav":
            self.in_navigation = False


def test_primary_navigation_is_identical_on_every_page():
    docs = Path(__file__).parents[1] / "docs"

    for page, current_path in PAGES.items():
        parser = NavigationParser()
        parser.feed((docs / page).read_text(encoding="utf-8"))

        assert [(link["href"], link["label"]) for link in parser.links] == EXPECTED_LINKS
        assert [link["href"] for link in parser.links if link["current"] == "page"] == [current_path]
