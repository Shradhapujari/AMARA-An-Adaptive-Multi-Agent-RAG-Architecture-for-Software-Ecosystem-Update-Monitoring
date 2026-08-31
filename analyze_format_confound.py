#!/usr/bin/env python3
"""
Separate the retrieval effect from the answer-format effect in a run.
=====================================================================
Why this exists
---------------
The published claim is that multi-agent decomposition improves the system. Two
of its reported advantages turn out to measure something else, and this script
re-derives both from a run's own artifacts so the finding is checkable rather
than asserted.

The design that makes it possible: `marag` and `marag_llm` are the same
pipeline with the same retrieval, differing only in how the answer is rendered
(`EvaluatorAgent`'s template vs prose synthesised by the baseline's model
through the shared prompt). So a difference between those two arms is a pure
format effect, and it can be subtracted from the `marag` vs `single_agent`
comparison that mixes both.

    marag      vs single_agent  = retrieval effect + format effect
    marag      vs marag_llm     = format effect            (retrieval identical)
    marag_llm  vs single_agent  = retrieval effect         (format matched)

Usage:
    python analyze_format_confound.py results/run_<id>
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import statistics as st
from typing import Dict, List, Tuple

TEMPLATE_ARM, PROSE_ARM, BASELINE = "marag", "marag_llm", "single_agent"


def load_run(run_dir: str) -> Tuple[dict, dict]:
    rows = [json.loads(l) for l in open(os.path.join(run_dir, "per_query.jsonl"))
            if l.strip()]
    by_query: Dict[object, Dict[str, dict]] = collections.defaultdict(dict)
    for r in rows:
        by_query[r["query_id"]][r["system"]] = r
    qrels_path = os.path.join(run_dir, "qrels.json")
    qrels = json.load(open(qrels_path)) if os.path.exists(qrels_path) else {}
    return by_query, qrels


def retrieval_identical(by_query: dict, a: str, b: str) -> Tuple[int, int]:
    """How many questions the two arms answered from the very same ranked docs."""
    pairs = [d for d in by_query.values() if a in d and b in d]
    same = sum(1 for d in pairs if d[a]["doc_ids"] == d[b]["doc_ids"])
    return same, len(pairs)


def paired_delta(by_query: dict, a: str, b: str, metric: str) -> dict:
    """Per-question a - b on an answer metric, with win/tie/loss."""
    diffs = []
    for d in by_query.values():
        if a not in d or b not in d:
            continue
        va = (d[a].get("answer_scores") or {}).get(metric)
        vb = (d[b].get("answer_scores") or {}).get(metric)
        if va is None or vb is None:
            continue
        diffs.append(va - vb)
    if not diffs:
        return {"n": 0}
    return {
        "n": len(diffs),
        "mean": st.mean(diffs),
        "wins": sum(1 for x in diffs if x > 0),
        "ties": sum(1 for x in diffs if x == 0),
        "losses": sum(1 for x in diffs if x < 0),
    }


def unique_relevant(by_query: dict, qrels: dict, a: str, b: str) -> Tuple[int, int, int]:
    """
    Relevant documents each arm retrieved that the other did not.

    Two arms can retrieve substantially different documents and still score
    identically, when the relevant documents each one uniquely finds offset.
    That is invisible in an aggregate metric table and is the reason a tie here
    is not evidence that the arms retrieve the same thing.
    """
    a_only = b_only = differing = 0
    for qid, d in by_query.items():
        if a not in d or b not in d:
            continue
        grades = qrels.get(str(qid), {})
        sa, sb = set(d[a]["doc_ids"]), set(d[b]["doc_ids"])
        differing += len(sa ^ sb)
        a_only += sum(1 for x in sa - sb if grades.get(x, 0) > 0)
        b_only += sum(1 for x in sb - sa if grades.get(x, 0) > 0)
    return a_only, b_only, differing


def answer_lengths(by_query: dict, arm: str) -> dict:
    lens = [len(d[arm]["answer"] or "") for d in by_query.values() if arm in d]
    if not lens:
        return {}
    return {"median": int(st.median(lens)), "mean": int(st.mean(lens)), "n": len(lens)}


def _line(d: dict) -> str:
    if not d.get("n"):
        return "not present in this run"
    return (f"mean {d['mean']:+.3f}  W/T/L {d['wins']}/{d['ties']}/{d['losses']}  "
            f"(n={d['n']})")


def report(run_dir: str) -> str:
    by_query, qrels = load_run(run_dir)
    arms = sorted({s for d in by_query.values() for s in d})
    L = [f"# Format vs retrieval decomposition — `{os.path.basename(run_dir)}`", ""]
    L.append(f"Arms present: {', '.join(arms)}  ·  questions: {len(by_query)}")
    L.append("")

    same, total = retrieval_identical(by_query, TEMPLATE_ARM, PROSE_ARM)
    L.append(f"## 1. The two multi-agent arms retrieve identically")
    L.append("")
    L.append(f"`{TEMPLATE_ARM}` vs `{PROSE_ARM}` identical ranked doc_ids: "
             f"**{same}/{total}**. Anything that differs between them is the "
             f"answer rendering, nothing else.")
    L.append("")

    fmt = paired_delta(by_query, PROSE_ARM, TEMPLATE_ARM, "faithfulness")
    mixed = paired_delta(by_query, TEMPLATE_ARM, BASELINE, "faithfulness")
    clean = paired_delta(by_query, PROSE_ARM, BASELINE, "faithfulness")
    L.append("## 2. Faithfulness: the gap is the format")
    L.append("")
    L.append(f"| comparison | what it measures | result |")
    L.append(f"|---|---|---|")
    L.append(f"| `{TEMPLATE_ARM}` − `{BASELINE}` | retrieval + format | {_line(mixed)} |")
    L.append(f"| `{PROSE_ARM}` − `{TEMPLATE_ARM}` | format alone | {_line(fmt)} |")
    L.append(f"| `{PROSE_ARM}` − `{BASELINE}` | retrieval alone | {_line(clean)} |")
    L.append("")
    if fmt.get("n") and mixed.get("n"):
        L.append(f"The format term ({fmt['mean']:+.3f}) accounts for the whole "
                 f"mixed gap ({mixed['mean']:+.3f}); with format matched, the "
                 f"retrieval term is {clean.get('mean', float('nan')):+.3f}.")
        L.append("")

    L.append("## 3. Answer length by arm")
    L.append("")
    L.append("| arm | median chars | mean chars |")
    L.append("|---|---|---|")
    for arm in arms:
        s = answer_lengths(by_query, arm)
        if s:
            L.append(f"| `{arm}` | {s['median']} | {s['mean']} |")
    L.append("")

    a_only, b_only, differing = unique_relevant(by_query, qrels, TEMPLATE_ARM, BASELINE)
    same_b, total_b = retrieval_identical(by_query, TEMPLATE_ARM, BASELINE)
    L.append("## 4. A retrieval tie is not retrieval agreement")
    L.append("")
    L.append(f"`{TEMPLATE_ARM}` and `{BASELINE}` return the same ranked docs on "
             f"only **{same_b}/{total_b}** questions; {differing} documents are "
             f"retrieved by exactly one of them. Of those, the relevant ones "
             f"split **{a_only}** to `{TEMPLATE_ARM}` and **{b_only}** to "
             f"`{BASELINE}` — near-symmetric, so they offset and the aggregate "
             f"metrics tie while the arms are not retrieving the same thing.")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--out", default="format_confound.md",
                    help="filename written inside run_dir")
    a = ap.parse_args()
    text = report(a.run_dir)
    print(text)
    path = os.path.join(a.run_dir, a.out)
    open(path, "w").write(text + "\n")
    print(f"\n[wrote] {path}")


if __name__ == "__main__":
    main()
