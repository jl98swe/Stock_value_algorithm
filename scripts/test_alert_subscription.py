#!/usr/bin/env python3
"""Manual subscription smoke test; never prints email or confirmation tokens."""
import json
import os
import urllib.error
import urllib.request
import urllib.parse

base = os.environ["SUPABASE_URL"].rstrip("/")
email = os.environ["TEST_ALERT_EMAIL"].strip()
payload = {
    "email": email,
    "consent": True,
    "channels": ["email"],
    "topics": ["signals"],
    "strategy": "all",
    "tickers": [],
}
request = urllib.request.Request(
    base + "/functions/v1/alerts/subscribe",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json", "Origin": "https://jl98swe.github.io"},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=25) as response:
        status = response.status
        body = json.loads(response.read(4096))
except urllib.error.HTTPError as exc:
    print("Subscription endpoint HTTP status:", exc.code)
    raise SystemExit(1) from None
except (urllib.error.URLError, TimeoutError) as exc:
    print("Subscription endpoint unreachable:", type(exc).__name__)
    raise SystemExit(1) from None
print("Subscription endpoint HTTP status:", status)
if status != 200 or "message" not in body:
    raise SystemExit("Unexpected subscription response")
print("Endpoint accepted request; verifying private queue.")
service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
query = base + "/rest/v1/alert_email_queue?select=id,status&recipient=eq." + urllib.parse.quote(email, safe="") + "&order=created_at.desc&limit=1"
queue_request = urllib.request.Request(query, headers={
    "apikey": service_key,
    "Authorization": "Bearer " + service_key,
    "Accept": "application/json",
})
try:
    with urllib.request.urlopen(queue_request, timeout=25) as response:
        rows = json.loads(response.read(4096))
except urllib.error.HTTPError as exc:
    print("Queue verification HTTP status:", exc.code)
    raise SystemExit(1) from None
if not rows:
    raise SystemExit("No queued message found. Possible existing subscription, cooldown, or capacity limit.")
print("Queue record found. Status:", rows[0]["status"])
print("Run 'Send queued alert confirmation email' manually to deliver it.")
