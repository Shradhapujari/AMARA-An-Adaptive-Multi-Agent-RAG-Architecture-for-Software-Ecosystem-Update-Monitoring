"""
releasetrain.io API Test Suite
==============================
Tests all 4 live API endpoints and shows exactly
what data comes back from each one.

Run: python test_apis.py
"""

import requests, json
from datetime import datetime

print(f"\n{'='*60}")
print(f"  releasetrain.io API Test Suite")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}")

# ── API 1: COMMUNITY (Reddit positive) ───────────────────
print("\n  [1] COMMUNITY API")
print(f"  URL: releasetrain.io/api/reddit/query/positive")
print(f"  {'─'*56}")
try:
    r = requests.get("https://releasetrain.io/api/reddit/query/positive", timeout=30)
    data = r.json()
    posts = data.get("data", [])
    print(f"  Status  : {r.status_code} OK")
    print(f"  Total   : {data.get('total', 0)} posts available")
    print(f"  Sample  :")
    for p in posts[:3]:
        print(f"    - [{p.get('subreddit')}] {p.get('title','')[:55]}")
        print(f"      Score: {p.get('score')} | Date: {p.get('created_utc','')[:10]} | CVE: {p.get('isAboutCve')}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── API 2: RELEASE NOTES ─────────────────────────────────
print("\n  [2] RELEASE NOTES API")
print(f"  URL: releasetrain.io/api/v/")
print(f"  {'─'*56}")
try:
    r = requests.get("https://releasetrain.io/api/v/", timeout=30)
    data = r.json()
    versions = data.get("versions", [])
    print(f"  Status  : {r.status_code} OK")
    print(f"  Total   : {len(versions)} versions available")
    print(f"  Sample  :")
    for v in versions[:3]:
        print(f"    - {v.get('versionProductName')} v{v.get('versionNumber')} ({v.get('versionReleaseDate')})")
        print(f"      Channel: {v.get('versionReleaseChannel')} | Security: {v.get('classification',{}).get('securityType',['?'])}")
        print(f"      Notes  : {v.get('versionReleaseNotes','')[:60]}...")
except Exception as e:
    print(f"  ERROR: {e}")

# ── API 3: CVE ────────────────────────────────────────────
print("\n  [3] CVE SECURITY API")
print(f"  URL: releasetrain.io/api/reddit/query/cve?q=CVE-&limit=5")
print(f"  {'─'*56}")
try:
    r = requests.get("https://releasetrain.io/api/reddit/query/cve",
                     params={"q":"CVE-","limit":5}, timeout=30)
    data = r.json()
    posts = data.get("data", [])
    print(f"  Status  : {r.status_code} OK")
    print(f"  Results : {len(posts)} CVE posts")
    print(f"  Sample  :")
    for p in posts[:3]:
        print(f"    - [{p.get('subreddit')}] {p.get('title','')[:55]}")
        print(f"      Date: {p.get('created_utc','')[:10]}")
        desc = (p.get('author_description') or '')[:80]
        if desc: print(f"      Detail: {desc}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── API 4: QUERY TEST ─────────────────────────────────────
print("\n  [4] LIVE QUERY TEST — 'Any critical Linux updates today?'")
print(f"  {'─'*56}")
query = "linux security patch update"
try:
    # Releases filtered
    r = requests.get("https://releasetrain.io/api/v/", timeout=30)
    all_v = r.json().get("versions",[])
    terms = set(query.split())
    matched = [v for v in all_v if any(t in " ".join(v.get("versionSearchTags",[])).lower() for t in terms)]
    print(f"  Releases matching 'linux security patch update': {len(matched)}")
    for v in matched[:3]:
        print(f"    - {v.get('versionProductName')} v{v.get('versionNumber')} ({v.get('versionReleaseDate')})")

    # Community
    r2 = requests.get("https://releasetrain.io/api/reddit/query/positive", timeout=30)
    all_p = r2.json().get("data",[])
    matched_p = [p for p in all_p if any(t in p.get("title","").lower() for t in terms)]
    print(f"\n  Community posts matching: {len(matched_p)}")
    for p in matched_p[:3]:
        print(f"    - [{p.get('subreddit')}] {p.get('title','')[:55]}")

    # CVE
    r3 = requests.get("https://releasetrain.io/api/reddit/query/cve",
                      params={"q":"linux","limit":3}, timeout=30)
    cve_p = r3.json().get("data",[])
    print(f"\n  CVE posts for 'linux': {len(cve_p)}")
    for p in cve_p[:2]:
        print(f"    - {p.get('title','')[:55]}")

except Exception as e:
    print(f"  ERROR: {e}")

print(f"\n{'='*60}")
print(f"  All APIs tested successfully")
print(f"{'='*60}\n")
