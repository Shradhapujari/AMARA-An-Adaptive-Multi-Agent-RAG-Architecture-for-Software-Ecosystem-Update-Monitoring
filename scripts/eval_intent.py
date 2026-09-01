#!/usr/bin/env python3
"""
Score the intent filter against real user questions.
====================================================
Source: `/api/reddit/query/questions?where=either`, 5,189 posts that upstream
has already predicted to be update-related, each carrying an `isAboutCve` flag.

The flag is the only per-post label available, and this script's main job is to
show why it cannot be used as intent ground truth rather than to report a score
against it. Measured over the first 200 posts (2026-09-01):

    posts labelled isAboutCve      37 / 200
    posts whose title contains any
    security word at all            5 / 200

A label that fires on 37 posts when only 5 mention security is not labelling
"this is a security question" -- it is labelling something closer to "this post
touches a product that has a CVE on file". Titles it marks positive include
"How to limit battery charge?" and "Anyone Else Having Trouble Keeping Up?".
Tuning a question-intent classifier to agree with it would mean firing the
security route on questions that contain no security content, which is the
opposite of what the filter is for.

So the classifier is scored two ways, and both are reported:

  1. against `isAboutCve`, as a precision figure only -- when this classifier
     does call a post a security question, how often does upstream agree;
  2. against the project's own benchmark questions, which are the distribution
     the demo is actually asked about, as a label distribution plus the
     abstention rate.

Usage:
    python -m scripts.eval_intent                  # fetch, cache, score
    python -m scripts.eval_intent --offline        # score from the cache only
    python -m scripts.eval_intent --pages 5        # 1,000 posts instead of 200
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.parse
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import intent  # noqa: E402

QUESTIONS_URL = "https://releasetrain.io/api/reddit/query/questions"
CACHE = os.path.join(_ROOT, "data", "reddit_questions.json")

# Any of these appearing in a title means the author raised security. Used only
# to characterise the upstream label, never as a classifier.
_SECURITY_WORDS = ("cve", "vulnerab", "exploit", "security", "malware",
                   "ransomware", "breach", "zero-day", "zeroday", "rce")


def fetch(pages: int = 1, limit: int = 200) -> list:
    """Pull `pages` of questions, newest first. 500 per page truncates."""
    out = []
    for page in range(1, pages + 1):
        params = {"where": "either", "limit": limit, "page": page,
                  "showCount": "true"}
        url = f"{QUESTIONS_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            payload = json.load(resp)
        rows = payload.get("data", [])
        out.extend(rows)
        pg = payload.get("pagination", {})
        if not pg.get("hasNext"):
            break
    return out


def load(offline: bool, pages: int) -> list:
    if offline:
        if not os.path.exists(CACHE):
            raise SystemExit(f"no cache at {CACHE}; run without --offline once")
        with open(CACHE, encoding="utf-8") as fh:
            return json.load(fh)
    rows = fetch(pages=pages)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    return rows


def has_security_word(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in _SECURITY_WORDS)


def score_reddit(rows: list) -> dict:
    tp = fp = fn = tn = 0
    for row in rows:
        title = row.get("title") or ""
        pred = intent.classify(title).label == "security"
        gold = bool(row.get("isAboutCve"))
        if pred and gold:
            tp += 1
        elif pred and not gold:
            fp += 1
        elif gold:
            fn += 1
        else:
            tn += 1
    return {
        "n": len(rows),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "gold_positive": tp + fn,
        "titles_with_security_word": sum(
            1 for r in rows if has_security_word(r.get("title") or "")),
        "labels": collections.Counter(
            intent.classify(r.get("title") or "").label for r in rows),
    }


def score_benchmark(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    items = payload if isinstance(payload, list) else \
        payload.get("questions", payload.get("data", []))
    questions = [q.get("query") or q.get("question") for q in items]
    questions = [q for q in questions if q]
    labels = collections.Counter(intent.classify(q).label for q in questions)
    return {"n": len(questions), "labels": labels,
            "abstained": labels.get("unknown", 0)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true",
                    help="score from the cached questions, no network")
    ap.add_argument("--pages", type=int, default=1,
                    help="pages of 200 questions to fetch (default 1)")
    ap.add_argument("--benchmark",
                    default=os.path.join(_ROOT, "data", "benchmark_100.json"))
    args = ap.parse_args()

    rows = load(args.offline, args.pages)
    r = score_reddit(rows)

    print(f"Reddit questions (/api/reddit/query/questions), n={r['n']}")
    print(f"  predicted labels          {dict(r['labels'])}")
    print(f"  upstream isAboutCve=true  {r['gold_positive']}")
    print(f"  titles naming security    {r['titles_with_security_word']}")
    print(f"  precision vs isAboutCve   {r['precision']:.2f} "
          f"(tp={r['tp']} fp={r['fp']})")
    print()
    print("  Recall against isAboutCve is deliberately not reported as a")
    print("  classifier score: the label fires on far more posts than mention")
    print("  security at all, so agreeing with it would mean routing")
    print("  security-free questions to the advisory feed.")

    if os.path.exists(args.benchmark):
        b = score_benchmark(args.benchmark)
        print()
        print(f"Project benchmark ({os.path.basename(args.benchmark)}), n={b['n']}")
        print(f"  labels     {dict(b['labels'])}")
        print(f"  abstained  {b['abstained']}/{b['n']} "
              f"({b['abstained'] / b['n']:.0%}) -> searched every pool")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
