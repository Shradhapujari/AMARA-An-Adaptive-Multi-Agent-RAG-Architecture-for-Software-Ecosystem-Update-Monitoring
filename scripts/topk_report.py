#!/usr/bin/env python3
"""Does raising top_k convert marag's fetch advantage into final retrieval?

Background. On the n=100 frozen ablation the multi-agent arm held 520 judged
relevant documents in its candidate pool against the baseline's 434 -- including
110 the baseline never fetched -- yet shipped 145 in top_k against the
baseline's 150. Pool recall separated cleanly (0.979 vs 0.845); recall@5 and
nDCG@3 did not. The obvious reading, "the reranker is worse", did not survive a
matched-ceiling control (diff -0.049, p=0.16), because marag's pool is 1.48x
larger and competes for the same 4 slots. That leaves top_k=4 as the suspected
throttle.

This reads the top_k sweep's run directories and asks, at each top_k:
  * does the arm gap in recall@k open up as k grows?
  * how much of each arm's pool ceiling is converted?
  * on the matched-ceiling subset, where fetch is equal, do the arms differ?

The harness only ever writes k=1,3,5, so recall/nDCG at larger k are recomputed
here from doc_ids + qrels. Reads artifacts only; runs nothing.

Produced by scripts/phase_topk.sh.

Usage:
    ./venv311/bin/python scripts/topk_report.py [run_dir ...]

With no arguments it auto-detects the newest judge-pool run per top_k value on
a benchmark_100 dataset.
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

from eval_harness.compare import paired_t_test, paired_bootstrap  # noqa: E402

A, B = "marag", "single_agent"
KS = (1, 3, 5, 10, 20)


def load_qrels(run):
    raw = json.load(open(os.path.join(run, "qrels.json")))
    if raw and all(isinstance(v, dict) for v in raw.values()):
        return {str(k): v for k, v in raw.items()}          # post-fix shape
    out = {}                                                # legacy flat cache
    for k, g in raw.items():
        qid, did = k.split(":", 1)
        out.setdefault(qid, {})[did] = int(g)
    return out


def dedup(seq):
    return list(dict.fromkeys(seq))


def recall_at(ranked, rel, k):
    if not rel:
        return None
    return len(set(ranked[:k]) & rel) / len(rel)


def ndcg_at(ranked, grades, k):
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum(((2 ** g) - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    if not idcg:
        return None
    dcg = sum(((2 ** grades.get(d, 0)) - 1) / math.log2(i + 2)
              for i, d in enumerate(ranked[:k]))
    return dcg / idcg


def summarize(run):
    cfg = json.load(open(os.path.join(run, "config.json")))
    rows = [json.loads(l) for l in open(os.path.join(run, "per_query.jsonl"))]
    qrels = load_qrels(run)
    idx = {}
    for r in rows:
        idx.setdefault(r["query_id"], {})[r["system"]] = r

    out = {"run": os.path.basename(run), "top_k": cfg.get("top_k"),
           "n": 0, "per_k": {}, "pool": {A: [], B: []},
           "conv": {A: [], B: []}, "matched": []}
    paired = {k: {A: [], B: []} for k in KS}
    nd = {k: {A: [], B: []} for k in KS}

    for q, per in sorted(idx.items()):
        if A not in per or B not in per:
            continue
        grades = qrels.get(str(q), {})
        rel = {d for d, g in grades.items() if g >= 1}
        if not rel:
            continue
        out["n"] += 1
        held = {}
        for s in (A, B):
            r = per[s]
            ranked = dedup(r["doc_ids"])
            pool = set(r.get("pool_doc_ids") or ranked)
            out["pool"][s].append(len(pool & rel) / len(rel))
            h = len(pool & rel)
            held[s] = h
            if h:
                out["conv"][s].append(len(set(ranked) & rel) / h)
            for k in KS:
                v = recall_at(ranked, rel, k)
                if v is not None:
                    paired[k][s].append(v)
                v2 = ndcg_at(ranked, grades, k)
                if v2 is not None:
                    nd[k][s].append(v2)
        if held[A] == held[B] and held[A] > 0:
            out["matched"].append((
                len(set(dedup(per[A]["doc_ids"])) & rel),
                len(set(dedup(per[B]["doc_ids"])) & rel)))

    for k in KS:
        a, b = paired[k][A], paired[k][B]
        if len(a) != len(b) or len(a) < 2:
            continue
        t = paired_t_test(a, b)
        bs = paired_bootstrap(a, b, iters=10000)
        na, nb = nd[k][A], nd[k][B]
        out["per_k"][k] = {
            "recall": (st.mean(a), st.mean(b), t["mean_diff"], t["p"],
                       bs["ci_low"], bs["ci_high"]),
            "ndcg": (st.mean(na), st.mean(nb)) if na and nb else None,
        }
    return out


def main(runs):
    if not runs:
        cand = []
        for d in sorted(glob.glob("results/run_*")):
            c = os.path.join(d, "config.json")
            pq = os.path.join(d, "per_query.jsonl")
            if not (os.path.exists(c) and os.path.exists(pq)):
                continue
            cfg = json.load(open(c))
            if (cfg.get("top_k") in (4, 10, 20)
                    and cfg.get("judge_pool")
                    and "benchmark_100" in str(cfg.get("dataset", ""))):
                cand.append((os.path.getmtime(d), d))
        # newest run per top_k
        best = {}
        for mt, d in sorted(cand):
            best[json.load(open(os.path.join(d, "config.json")))["top_k"]] = d
        runs = [best[k] for k in sorted(best)]

    if not runs:
        print("no top_k sweep run directories found yet")
        return 1

    reports = [summarize(r) for r in runs]

    print("=" * 82)
    print("TOP_K SWEEP — does a wider slot budget convert the fetch advantage?")
    print("=" * 82)
    for rep in reports:
        print(f"\n### top_k = {rep['top_k']}   ({rep['run']}, n={rep['n']} scorable)")
        print(f"  pool recall (ceiling) : {A} {st.mean(rep['pool'][A]):.3f}   "
              f"{B} {st.mean(rep['pool'][B]):.3f}")
        print(f"  conversion held->shipped: {A} {st.mean(rep['conv'][A]):.3f}   "
              f"{B} {st.mean(rep['conv'][B]):.3f}")
        if rep["matched"]:
            sa = [m[0] for m in rep["matched"]]
            sb = [m[1] for m in rep["matched"]]
            tm = paired_t_test(sa, sb)
            print(f"  matched-ceiling subset  : n={len(sa)}  "
                  f"shipped {st.mean(sa):.3f} vs {st.mean(sb):.3f}  "
                  f"diff {tm['mean_diff']:+.3f}  p={tm['p']:.4f}")
        print(f"  {'k':>4} {'recall ' + A:>16} {'recall ' + B:>16} "
              f"{'diff':>8} {'p':>8}  95% CI")
        for k in KS:
            d = rep["per_k"].get(k)
            if not d:
                continue
            ma, mb, diff, p, lo, hi = d["recall"]
            star = " *" if (lo > 0 or hi < 0) else ""
            print(f"  {k:>4} {ma:>16.3f} {mb:>16.3f} {diff:>+8.3f} {p:>8.4f}  "
                  f"[{lo:+.3f}, {hi:+.3f}]{star}")

    print("\n" + "=" * 82)
    print("READING")
    print("=" * 82)
    print("""  If the marag-minus-baseline recall gap grows with top_k and its CI clears
  zero at k=10 or 20 while sitting on zero at k=4, then top_k was the throttle:
  the fetch advantage is real and the slot budget was hiding it.

  If the gap stays flat and CI-crossing at every k while marag's pool recall
  stays far above the baseline's, then the extra documents are being ranked
  below the baseline's, and the deficit is in ranking after all -- which the
  matched-ceiling row tests directly at equal fetch.

  A * marks a CI that excludes zero. Treat anything else as not detectable at
  this n, not as a null.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
