#!/usr/bin/env python3
"""
Before/after on the questions the demo got wrong.
=================================================
Runs a set of questions twice against the same live pool -- once the way the
demo retrieved before this change, once through `grounding.ground` -- and
prints the answer each path supports, with the source behind it.

The point is to show that the failures were retrieval failures. The demo's
"Linux v25.642087.0" reads as a hallucination and is not one: that string is
verbatim from `/api/v/?q=Linux`, where 449 of 606 rows are NVD CVE records
whose `versionNumber` is an affected-version string rather than a release.
The ungrounded path sorts those rows by date and reports the newest, which is
always an advisory, because advisories are filed daily and kernel releases are
not.

Usage:
    python -m scripts.grounding_report                    # live, all questions
    python -m scripts.grounding_report --markdown out.md  # write a report
    python -m scripts.grounding_report --question "..."   # one question
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from typing import Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import vendor  # noqa: E402
from grounding import ground  # noqa: E402

RELEASES_API = "https://releasetrain.io/api/v/"

# The questions the demo answered wrongly, plus the advisor's worked example.
# Each carries what is wrong with the ungrounded answer, so the report says
# what the reader should be looking at.
CASES = [
    ("What is the latest Linux version?",
     "answered with an NVD affected-version string instead of a kernel release"),
    ("Any critical Linux updates today?",
     "answered with advisories only; no shipped release was distinguished"),
    ("What bugs were fixed in Chrome recently?",
     "sentence-shaped query returns zero release rows"),
    ("Any security vulnerabilities in Python?",
     "advisories are the right pool here — the grounded path should agree"),
]


def fetch_releases(q: str, limit: int = 100) -> List[Dict]:
    url = f"{RELEASES_API}?{urllib.parse.urlencode({'q': q, 'limit': limit})}"
    try:
        with urllib.request.urlopen(url, timeout=45) as resp:
            payload = json.load(resp)
    except Exception as exc:                       # offline host, bad gateway
        print(f"    ! fetch failed for q={q!r}: {exc}", file=sys.stderr)
        return []
    return [{
        "product": v.get("versionProductName", ""),
        "version": v.get("versionNumber", ""),
        "date":    str(v.get("versionReleaseDate", "")),
        "notes":   (v.get("versionReleaseNotes") or "")[:160],
        "url":     v.get("versionUrl", ""),
        "isCve":   v.get("isCve"),
    } for v in payload.get("versions", [])]


def newest(rows: List[Dict]) -> Dict:
    return max(rows, key=lambda r: r["date"]) if rows else {}


def cite(row: Dict) -> str:
    if not row:
        return "— nothing retrieved —"
    kind = vendor.classify_record(row)
    return (f"{vendor.describe_record(row)} ({row['date']}) "
            f"[{kind}] {row['url']}")


def run_case(question: str, note: str, catalog, today: date) -> Dict:
    g = ground(question, now=today, catalog=catalog)

    # Before: the question as typed, straight at the endpoint, newest first.
    before_rows = fetch_releases(question)
    before = newest(before_rows)

    # After: fetch on the grounded phrasings, keep only shipped releases when
    # the question is a release question, and only the product asked about.
    after_rows: List[Dict] = []
    seen = set()
    for phrase in g.retrieval_phrasings:
        for row in fetch_releases(phrase):
            key = (row["url"], row["version"], row["date"])
            if key not in seen:
                seen.add(key)
                after_rows.append(row)

    scoped = vendor.filter_by_vendor(after_rows, g.vendors)
    if "cve" not in g.citable_kinds:
        scoped = [r for r in scoped if vendor.is_release_record(r)]
    after = newest(scoped)

    return {
        "question": question, "note": note,
        "rewritten": g.rewritten,
        "vendors": g.vendor_names,
        "intent": g.intent.label,
        "citable": list(g.citable_kinds),
        "before_n": len(before_rows), "before": before,
        "after_n": len(scoped), "after": after,
        "advisories_dropped": sum(
            1 for r in after_rows if not vendor.is_release_record(r))
        if "cve" not in g.citable_kinds else 0,
    }


def as_text(r: Dict) -> str:
    return "\n".join([
        f"Q  {r['question']}",
        f"   ({r['note']})",
        f"   rewritten : {r['rewritten']}",
        f"   vendors   : {r['vendors'] or '—'}   intent: {r['intent']}"
        f"   citable: {', '.join(r['citable'])}",
        f"   BEFORE ({r['before_n']} rows on the raw question)",
        f"      {cite(r['before'])}",
        f"   AFTER  ({r['after_n']} rows after grounding"
        + (f", {r['advisories_dropped']} advisories excluded" if r["advisories_dropped"] else "")
        + ")",
        f"      {cite(r['after'])}",
    ])


def as_markdown(rows: List[Dict], today: date) -> str:
    out = [f"# Grounding: before and after\n",
           f"Live pool, {today.isoformat()}. `before` is the question sent to "
           f"`/api/v/` as typed; `after` is the same pool retrieved through "
           f"`grounding.ground`, vendor-filtered, and record-type filtered "
           f"when the question is not a security question.\n"]
    for r in rows:
        out.append(f"## {r['question']}\n")
        out.append(f"*{r['note']}*\n")
        out.append(f"- rewritten: `{r['rewritten']}`")
        out.append(f"- vendors: `{r['vendors']}` · intent: `{r['intent']}` · "
                   f"citable: `{', '.join(r['citable'])}`")
        out.append(f"- **before** ({r['before_n']} rows): {cite(r['before'])}")
        out.append(f"- **after** ({r['after_n']} rows"
                   + (f", {r['advisories_dropped']} advisories excluded"
                      if r["advisories_dropped"] else "")
                   + f"): {cite(r['after'])}\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question", action="append",
                    help="run one question instead of the built-in cases")
    ap.add_argument("--markdown", help="also write a markdown report here")
    ap.add_argument("--date", help="as-of date, YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    catalog = vendor.load_catalog()
    cases = [(q, "ad hoc") for q in args.question] if args.question else CASES

    rows = []
    for question, note in cases:
        r = run_case(question, note, catalog, today)
        rows.append(r)
        print(as_text(r))
        print()

    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(as_markdown(rows, today))
        print(f"wrote {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
