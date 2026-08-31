#!/usr/bin/env python3
"""
Paired significance and interval estimates for the two-metric inversion.

The inversion reported in the paper (Table~\ref{tab:inversion}) rests on ten
ground-truth validation questions. Ten is small enough that a reviewer is right
to ask whether the deficit is distinguishable from sampling noise, so this
script answers that from the per-query rows rather than from the aggregates.

Because n is small the tests are exact, not asymptotic: the null distribution is
enumerated over all 2^n sign assignments instead of approximated. Two facts the
caller needs and neither p-value carries on its own:

  * With m nonzero pairs, the smallest attainable two-sided p is 2 / 2^m. At
    m = 7 that floor is 0.0156, so a "significant" result there is significant
    at the resolution limit of the design, not by a comfortable margin. The
    script prints the floor next to every p-value.
  * The bootstrap interval is wide at this n. It supports the sign and rough
    scale of the deficit; it does not pin the magnitude.

Usage:
    ./venv311/bin/python scripts/inversion_stats.py
    ./venv311/bin/python scripts/inversion_stats.py <run_dir> [--a marag] [--b single_agent]
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The run behind Table~\ref{tab:inversion}: substring-boost ranking, rewritten
# phrasing only, the configuration the conference version shipped.
DEFAULT_RUN = os.path.join(ROOT, "results", "run_1788128243_237950e265eb")

METRICS = ["ndcg@1", "ndcg@3", "ndcg@5", "mrr", "recall@5"]
BOOTSTRAP_RESAMPLES = 100_000
BOOTSTRAP_SEED = 20260831
EXACT_LIMIT = 22  # 2^22 sign assignments is a few seconds; past that, sample


def load_paired(run_dir: str, sys_a: str, sys_b: str):
    """Return (query_ids, {system: {query_id: ir_dict}}) for the two systems."""
    path = os.path.join(run_dir, "per_query.jsonl")
    by: dict[str, dict[str, dict]] = {}
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            name = row.get("system") or row.get("generator")
            by.setdefault(name, {})[row["query_id"]] = row.get("ir") or {}
    for name in (sys_a, sys_b):
        if name not in by:
            raise SystemExit(f"{run_dir}: no rows for system {name!r} (have {sorted(by)})")
    shared = sorted(set(by[sys_a]) & set(by[sys_b]))
    if not shared:
        raise SystemExit(f"{run_dir}: {sys_a} and {sys_b} share no query_id")
    return shared, by


def sign_flips(n: int, seed: int = BOOTSTRAP_SEED):
    """All 2^n sign vectors when that is tractable, else a random sample."""
    if n <= EXACT_LIMIT:
        return itertools.product((1, -1), repeat=n), True
    rnd = random.Random(seed)
    sampled = (tuple(rnd.choice((1, -1)) for _ in range(n)) for _ in range(BOOTSTRAP_RESAMPLES))
    return sampled, False


def permutation_p(diffs: list[float]) -> tuple[float, bool]:
    """Two-sided sign-flip test on the mean paired difference."""
    observed = abs(st.mean(diffs))
    hits = total = 0
    flips, exact = sign_flips(len(diffs))
    for signs in flips:
        total += 1
        flipped = st.mean([s * d for s, d in zip(signs, diffs)])
        if abs(flipped) >= observed - 1e-12:
            hits += 1
    return hits / total, exact


def signed_ranks(nonzero: list[float]) -> list[float]:
    """Ranks of |d|, ties averaged."""
    m = len(nonzero)
    order = sorted(range(m), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * m
    i = 0
    while i < m:
        j = i
        while j + 1 < m and abs(abs(nonzero[order[j + 1]]) - abs(nonzero[order[i]])) < 1e-12:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def wilcoxon_p(diffs: list[float]) -> tuple[float, float, int, bool]:
    """Exact two-sided Wilcoxon signed-rank test. Zero differences are dropped,
    which is what shrinks the effective sample and raises the p-value floor."""
    nonzero = [d for d in diffs if abs(d) > 1e-12]
    m = len(nonzero)
    if m == 0:
        return 1.0, 0.0, 0, True
    ranks = signed_ranks(nonzero)
    total_rank = sum(ranks)
    w_plus = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    w_observed = min(w_plus, total_rank - w_plus)
    hits = total = 0
    flips, exact = sign_flips(m)
    for signs in flips:
        total += 1
        plus = sum(r for s, r in zip(signs, ranks) if s > 0)
        if min(plus, total_rank - plus) <= w_observed + 1e-12:
            hits += 1
    return hits / total, w_observed, m, exact


def bootstrap_ci(diffs: list[float], resamples: int = BOOTSTRAP_RESAMPLES):
    """Percentile bootstrap interval for the mean paired difference."""
    rnd = random.Random(BOOTSTRAP_SEED)
    n = len(diffs)
    means = sorted(st.mean([diffs[rnd.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", nargs="?", default=DEFAULT_RUN)
    ap.add_argument("--a", default="marag", help="system under test")
    ap.add_argument("--b", default="single_agent", help="baseline")
    args = ap.parse_args()

    queries, by = load_paired(args.run_dir, args.a, args.b)
    print(f"run:    {os.path.basename(args.run_dir.rstrip('/'))}")
    print(f"paired: n = {len(queries)} ({args.a} vs {args.b})\n")

    for metric in METRICS:
        a = [by[args.a][q].get(metric) for q in queries]
        b = [by[args.b][q].get(metric) for q in queries]
        if any(v is None for v in a + b):
            print(f"{metric}: not scored in this run\n")
            continue
        diffs = [x - y for x, y in zip(a, b)]
        mean_diff = st.mean(diffs)
        lo, hi = bootstrap_ci(diffs)
        p_perm, perm_exact = permutation_p(diffs)
        p_wil, w, m, wil_exact = wilcoxon_p(diffs)
        floor = 2 / (2 ** m) if m else 1.0
        dz = mean_diff / st.stdev(diffs) if len(diffs) > 1 and st.stdev(diffs) else float("nan")

        print(f"{metric}:  {args.a} {st.mean(a):.3f}   {args.b} {st.mean(b):.3f}")
        print(f"   mean paired difference {mean_diff:+.3f}   bootstrap 95% CI [{lo:+.3f}, {hi:+.3f}]")
        print(f"   Cohen's d_z {dz:+.2f}   nonzero pairs {m}/{len(diffs)}")
        print(f"   exact sign-flip p = {p_perm:.4f}{'' if perm_exact else ' (sampled)'}")
        print(f"   exact Wilcoxon  p = {p_wil:.4f} (W = {w:g}){'' if wil_exact else ' (sampled)'}")
        print(f"   smallest attainable two-sided p at {m} nonzero pairs = {floor:.4f}")
        print()


if __name__ == "__main__":
    main()
