"""Read-only Supabase subscriber readiness check. No email addresses are logged."""
import json
import os
import urllib.error
import urllib.request

base = os.environ["SUPABASE_URL"].rstrip("/")
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
if not base.startswith("https://") or not base.endswith(".supabase.co"):
    raise SystemExit("SUPABASE_URL must be a Supabase project URL, without /rest/v1")
request = urllib.request.Request(
    base + "/rest/v1/alert_subscribers?select=id,status&limit=5",
    headers={"apikey": key, "Authorization": "Bearer " + key, "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        rows = json.load(response)
except urllib.error.HTTPError as exc:
    raise SystemExit(f"Supabase request failed with HTTP {exc.code}") from None
if not isinstance(rows, list):
    raise SystemExit("Unexpected Supabase response")
print("Supabase connection OK; subscriber table accessible.")
print(f"Returned {len(rows)} records (limit 5). No addresses were read.")
if len(rows) > 4:
    print("WARNING: More than four subscriber records exist; check capacity policy.")
print("Read-only check finished. No messages sent.")
