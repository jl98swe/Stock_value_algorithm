"""Read-only Supabase subscriber readiness check. No email addresses are logged."""
import json
import os
import urllib.parse
import urllib.error
import urllib.request

base = os.environ["SUPABASE_URL"].rstrip("/")
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
if not key:
    raise SystemExit("Supabase key is empty")
print("Configured key type: " + ("modern secret" if key.startswith("sb_secret_") else "legacy JWT" if key.startswith("eyJ") else "unknown"))
print("Configured Supabase host: " + urllib.parse.urlparse(base).hostname)
if not base.startswith("https://") or not base.endswith(".supabase.co"):
    raise SystemExit("SUPABASE_URL must be a Supabase project URL, without /rest/v1")
request = urllib.request.Request(
    base + "/rest/v1/alert_subscribers?select=id,status&limit=5",
    headers={"apikey": key, "Accept": "application/json", "User-Agent": "StockValueAlerts-ReadOnlyCheck/1.0"},
)
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        rows = json.load(response)
except urllib.error.HTTPError as exc:
    # Only expose allowlisted diagnostic fields; never print full response or credentials.
    raw = exc.read(8192).decode("utf-8", errors="replace")
    try:
        error = json.loads(raw)
    except ValueError:
        error = {}
    safe_code = str(error.get("code", ""))[:80] if isinstance(error, dict) else ""
    known_codes = {"PGRST301", "PGRST302", "42501", "invalid_api_key", "bad_jwt", "not_admin", "permission_denied"}
    print("Supabase error category: " + (safe_code if safe_code in known_codes else "unclassified"))
    print("HTTP status: " + str(exc.code))
    print("Response content type: " + str(exc.headers.get("Content-Type", "unknown")).split(";")[0][:60])
    raise SystemExit("Supabase rejected the request; check key/project pairing and Data API exposure") from None
if not isinstance(rows, list):
    raise SystemExit("Unexpected Supabase response")
print("Supabase connection OK; subscriber table accessible.")
print(f"Returned {len(rows)} records (limit 5). No addresses were read.")
if len(rows) > 4:
    print("WARNING: More than four subscriber records exist; check capacity policy.")
print("Read-only check finished. No messages sent.")
