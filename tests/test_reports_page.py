from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reports_page_uses_approved_copy_and_tooltips() -> None:
    html = (ROOT / "docs" / "reports.html").read_text(encoding="utf-8")

    assert "Ingen spekulativ poängprognos" not in html
    assert "Så ska värdena läsas" not in html
    assert "Kvartals-EPS föregående år" in html
    assert "Rapporter inom 10 handelsdagar" in html
    assert "Dagar då börsen är stängd räknas inte." in html
    assert "Om publiceringsdatumet saknas används datumet då rapportens nya EPS TTM började användas och raden flaggas." in html
    assert './assets/reports.css?v=20260915-1' in html


def test_reports_page_uses_approved_dynamic_messages() -> None:
    script = (ROOT / "docs" / "assets" / "reports.js").read_text(encoding="utf-8")

    assert "Estimatet är inte jämförbart" in script
    assert "Saknas" not in script
    assert "Rapportdatum ej verifierat" in script
    assert "Inga bevakade aktier har ett registrerat rapportdatum inom de kommande tio handelsdagarna." in script
    assert "Inga verifierade rapporter finns under de senaste tjugo handelsdagarna." in script
