#!/usr/bin/env python3
"""
Stratified subset of data/benchmark_300.json
============================================
Why not `--limit N`
-------------------
benchmark_300.json is emitted grouped by ecosystem and category, so a prefix is
not a sample: the first 100 records are 60 `releases` + 40 `bugs` and contain
zero security, community, or general questions. Any per-category table built
from that prefix would be missing three of five categories.

What this does instead
----------------------
Picks N/5 questions per category, round-robin across ecosystems so coverage is
as wide as the source allows, and inside one (category, ecosystem) cell prefers
records that carry ground truth — those are the only ones on which correctness
and the deterministic benchmark scoring can be computed at all.

Records are copied **verbatim**. Nothing is rewritten, re-templated, or
invented; every provenance field (`source`, `source_endpoint`, `source_id`,
`mined`) travels with the record, so a subset row is auditable exactly like its
parent row. The selection is deterministic: same input file, same output.

Usage:
    python build_benchmark_subset.py                 # 100 questions
    python build_benchmark_subset.py --n 150 --out data/benchmark_150.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os

SRC = "data/benchmark_300.json"
OUT = "data/benchmark_100.json"


def file_hash(path: str) -> str:
    return hashlib.sha1(open(path, "rb").read()).hexdigest()[:12]


def select(records: list, n: int) -> list:
    """N/len(categories) per category, round-robin over ecosystems."""
    by_cat: dict = collections.defaultdict(list)
    for r in records:
        by_cat[r["category"]].append(r)

    categories = sorted(by_cat)
    per_cat, remainder = divmod(n, len(categories))
    picked: list = []

    for i, cat in enumerate(categories):
        want = per_cat + (1 if i < remainder else 0)
        # Ecosystem queues, each ordered ground-truth-first then by id so the
        # choice does not depend on dict iteration order.
        queues: dict = collections.defaultdict(list)
        for r in by_cat[cat]:
            queues[r["ecosystem"]].append(r)
        for eco in queues:
            queues[eco].sort(key=lambda r: (r.get("ground_truth") is None, r["id"]))

        taken: list = []
        ecos = sorted(queues)
        while len(taken) < want and any(queues[e] for e in ecos):
            for eco in ecos:
                if len(taken) == want:
                    break
                if queues[eco]:
                    taken.append(queues[eco].pop(0))
        if len(taken) < want:
            print(f"  ! {cat}: only {len(taken)} of {want} available")
        picked.extend(taken)

    return sorted(picked, key=lambda r: r["id"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()

    records = json.load(open(args.src))
    subset = select(records, args.n)

    cats = collections.Counter(r["category"] for r in subset)
    ecos = collections.Counter(r["ecosystem"] for r in subset)
    srcs = collections.Counter(r["source"] for r in subset)
    gt = sum(1 for r in subset if r.get("ground_truth"))

    json.dump(subset, open(args.out, "w"), indent=1)
    manifest = {
        "generated_by": os.path.basename(__file__),
        "parent": args.src,
        "parent_sha1_12": file_hash(args.src),
        "parent_n": len(records),
        "n": len(subset),
        "selection": "N/5 per category, round-robin over ecosystems, "
                     "ground-truth-bearing records first within a cell",
        "deterministic": True,
        "categories": dict(sorted(cats.items())),
        "ecosystems": dict(sorted(ecos.items())),
        "sources": dict(sorted(srcs.items())),
        "with_ground_truth": gt,
        "ids": [r["id"] for r in subset],
    }
    mpath = args.out.replace(".json", ".manifest.json")
    json.dump(manifest, open(mpath, "w"), indent=1)

    print(f"wrote {args.out}  ({len(subset)} questions, {gt} with ground truth)")
    print(f"      categories : {dict(sorted(cats.items()))}")
    print(f"      ecosystems : {len(ecos)} distinct, max {max(ecos.values())} per ecosystem")
    print(f"      sources    : {dict(sorted(srcs.items()))}")
    print(f"      manifest   : {mpath}")


if __name__ == "__main__":
    main()
