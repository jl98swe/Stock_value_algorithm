"""Validate and apply website submissions inside the existing serialized data job.

No browser credentials are accepted here. The Actions API authorizes the job;
all report fields are checked again before any data file is changed.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .add_report import add_report
from .config import ROOT
from .fx import load_stock_currencies
from .manual_eps import derive_manual_eps_ttm_safe
from .manual_reports import append_manual_submission, load_manual_submissions, publish_manual_reports
from .quarterly_eps import upsert_manual_quarterly_eps
from .utils import write_json_atomic


def validate_submission(payload: dict, *, today: date | None = None) -> dict:
    today = today or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    required = {"request_id", "ticker", "report_period", "period_end", "published_at", "metric", "value", "currency", "source", "notes"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("Inmatningen saknar fält eller innehåller okända fält")
    item = dict(payload)
    for key in required - {"value"}:
        if not isinstance(item[key], str):
            raise ValueError(f"{key} måste vara text")
        item[key] = item[key].strip()
    if not re.fullmatch(r"[a-f0-9]{32}", item["request_id"]):
        raise ValueError("Ogiltigt registrerings-id")
    metadata = load_stock_currencies()
    if item["ticker"] not in set(metadata["ticker"]):
        raise ValueError("Aktien finns inte i aktielistan")
    if not re.fullmatch(r"\d{4}-Q[1-4]", item["report_period"]):
        raise ValueError("Rapportperiod ska anges som ÅÅÅÅ-Q1 till Q4")
    dates = {}
    for key in ("period_end", "published_at"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item[key]):
            raise ValueError(f"{key} ska anges som ÅÅÅÅ-MM-DD")
        dates[key] = date.fromisoformat(item[key])
    if dates["period_end"] > dates["published_at"] or dates["published_at"] > today:
        raise ValueError("Periodslut får inte ligga efter rapportdatum och rapportdatum får inte ligga i framtiden")
    if item["metric"] not in {"eps_ttm", "quarterly_eps"}:
        raise ValueError("Välj EPS TTM eller kvartals-EPS")
    if isinstance(item["value"], bool) or not isinstance(item["value"], (int, float)) or not math.isfinite(item["value"]):
        raise ValueError("EPS måste vara ett ändligt tal")
    if not re.fullmatch(r"[A-Z]{3}", item["currency"]):
        raise ValueError("Ange en valutakod med tre bokstäver")
    if not item["source"] or len(item["source"]) > 250 or len(item["notes"]) > 2000:
        raise ValueError("Källa krävs (högst 250 tecken), notering får ha högst 2000 tecken")
    # Reserved metadata markers must never be supplied through free text.
    if any(re.search(r"report_currency\s*=|manual_report_submission_v1|tradingview_eps_manual_override_v1", item[key], re.I) for key in ("source", "notes")):
        raise ValueError("Källa och notering innehåller reserverad metadata")
    return item


def submit(payload: dict) -> dict:
    item = validate_submission(payload)
    request_id = item["request_id"]
    receipt_path = ROOT / "docs" / "data" / "manual_requests" / f"{request_id}.json"
    previous = load_manual_submissions()
    duplicates = previous.loc[previous["submission_id"].eq(request_id)]
    if not duplicates.empty:
        row = duplicates.iloc[-1]
        # A retry must never change the meaning of an already saved request.
        fields = {"ticker": "ticker", "report_period": "report_period", "period_end": "period_end", "published_at": "published_at", "metric": "input_metric", "currency": "eps_currency", "source": "source", "notes": "notes"}
        if any(str(row[target]) != str(item[key]) for key, target in fields.items()) or float(row["input_eps"]) != item["value"]:
            raise ValueError("Registrerings-id används redan för en annan inmatning")
        if receipt_path.exists():
            return json.loads(receipt_path.read_text(encoding="utf-8"))
        raise ValueError("Registreringen finns redan men kvittot saknas; kontrollera historiken")

    metadata = load_stock_currencies().set_index("ticker")
    price_currency = str(metadata.loc[item["ticker"], "price_currency"]).upper()
    reason = ""
    status = "applied"
    if item["currency"] != price_currency:
        status = "currency_review"
        reason = f"Inmatad EPS är i {item['currency']} och aktiekursen i {price_currency}. Ingen valutaomräkning eller ny TTM har tillämpats. Ange ett verifierat EPS TTM i {price_currency} för att uppdatera poängen."
    elif item["metric"] == "quarterly_eps":
        # Check before modifying any files. Only data/definition problems produce
        # a pending submission; I/O failures still fail the workflow.
        try:
            derived = derive_manual_eps_ttm_safe(ticker=item["ticker"], period_end=item["period_end"], current_period_eps=item["value"])
            if derived["eps_currency"] != item["currency"]:
                raise ValueError("Valutan i TTM-underlaget skiljer sig från inmatad EPS")
        except ValueError as error:
            status = "pending_ttm"
            reason = str(error)

    if status == "applied":
        reports = add_report(
            ticker=item["ticker"], report_period=item["report_period"], period_end=item["period_end"],
            published_at=item["published_at"], source=item["source"], notes=item["notes"],
            eps=item["value"] if item["metric"] == "quarterly_eps" else None,
            eps_ttm=item["value"] if item["metric"] == "eps_ttm" else None,
            eps_currency=item["currency"], submission_id=request_id,
        )
        result_ttm = float(reports.loc[(reports["ticker"] == item["ticker"]) & (reports["report_period"] == item["report_period"]), "eps_ttm"].iloc[-1])
    else:
        # Keep usable native-currency quarterly history even if TTM is blocked.
        if item["metric"] == "quarterly_eps":
            upsert_manual_quarterly_eps(ticker=item["ticker"], period_end=item["period_end"], report_date=item["published_at"], eps=item["value"], eps_currency=item["currency"], source=item["source"])
        append_manual_submission(
            ticker=item["ticker"], report_period=item["report_period"], period_end=item["period_end"],
            published_at=item["published_at"], effective_date=item["published_at"],
            input_metric=item["metric"], input_eps=item["value"], result_eps_ttm=None,
            eps_currency=item["currency"], source=item["source"], notes=item["notes"],
            submission_id=request_id, status=status, status_reason=reason,
        )
        publish_manual_reports()
        result_ttm = None
    receipt = {"request_id": request_id, "ticker": item["ticker"], "status": status, "reason": reason, "result_eps_ttm": result_ttm, "currency": item["currency"]}
    write_json_atomic(receipt_path, receipt)
    return receipt


def main() -> None:
    result = submit(json.loads(os.environ["EPS_SUBMISSION"]))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
