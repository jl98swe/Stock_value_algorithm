from __future__ import annotations

from pathlib import Path

from .utils import write_json_atomic


def write_split_dashboard(dashboard_file: Path, payload: dict[str, object]) -> None:
    """Write a small manifest plus one dashboard payload per ticker for the website."""
    target_dir = dashboard_file.parent / dashboard_file.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    stocks = payload.get("stocks")
    if not isinstance(stocks, dict):
        raise ValueError("dashboard-payload saknar stocks-objekt")

    files: dict[str, str] = {}
    expected: set[str] = {"index.json"}
    for ticker, stock in stocks.items():
        filename = f"{ticker}.json"
        files[str(ticker)] = filename
        expected.add(filename)
        write_json_atomic(target_dir / filename, stock)

    write_json_atomic(
        target_dir / "index.json",
        {"meta": payload.get("meta", {}), "files": files},
    )

    for old_file in target_dir.glob("*.json"):
        if old_file.name not in expected:
            old_file.unlink()
