"""Deliver queued confirmation messages through Gmail SMTP.

Manual dispatch initially. No scheduled send until end-to-end tests pass.
"""
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

base = os.environ["SUPABASE_URL"].rstrip("/")
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
sender = os.environ["GMAIL_ADDRESS"].strip()
password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "").strip()
headers = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json"}
queue = base + "/rest/v1/alert_email_queue"


def api(method, url, payload=None, extra=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={**headers, **(extra or {})}, method=method)
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


# Send only a single queued message per manual run, to minimize blast radius.
rows = api("GET", queue + "?select=id,recipient,subject,body,subscriber_id&status=eq.pending&order=created_at.asc&limit=1")
if not rows:
    print("No pending confirmation emails.")
    raise SystemExit(0)

item = rows[0]
# Only one runner may claim a given pending row.
claimed = api(
    "PATCH",
    queue + "?id=eq." + urllib.parse.quote(item["id"]) + "&status=eq.pending",
    {"status": "sending", "claimed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()},
    {"Prefer": "return=representation"},
)
if not claimed:
    print("Queue item already claimed.")
    raise SystemExit(0)

message = EmailMessage()
message["From"] = sender
message["To"] = item["recipient"]
message["Subject"] = item["subject"]
message.set_content(item["body"])
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
except Exception:
    api("PATCH", queue + "?id=eq." + urllib.parse.quote(item["id"]), {"status": "failed"})
    raise SystemExit("SMTP send failed. Queue item marked failed; review before retry.") from None
api("PATCH", queue + "?id=eq." + urllib.parse.quote(item["id"]), {"status": "sent", "sent_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
print("One queued confirmation email sent successfully.")
