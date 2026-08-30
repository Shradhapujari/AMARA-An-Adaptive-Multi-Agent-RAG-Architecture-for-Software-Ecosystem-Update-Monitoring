"""
Head-to-head system comparison with paired statistics.
=====================================================
The reviewers asked for a comparative evaluation showing what the multi-agent
decomposition actually contributes, measured against other systems rather than
against our own metric alone. `run_eval` already runs every system on the same
questions; this module does the statistics on that output.

Because every system answers the *same* question set, comparisons are paired,
which is both more powerful and more honest than comparing two independent
means. For each metric and each system-vs-baseline pair we report:

  * mean of each system and the mean paired difference
  * a paired t-test  (parametric; assumes roughly normal differences)
  * a paired bootstrap 95% CI and p-value (non-parametric; assumes nothing,
    and is the number to trust when n is small or the differences are skewed)
  * win / tie / loss counts, which say how *consistent* a gain is rather than
    how large — a system that wins by a lot on three questions and loses on
    thirty is not better, even if its mean is higher
  * Holm-corrected p-values across the family of comparisons, since testing
    several systems against one baseline inflates the false-positive rate

Everything is pure-Python (no scipy/numpy) so it runs wherever the harness runs.

Usage:
    python -m eval_harness.compare results/run_1234_abcdef
    python -m eval_harness.compare results/run_... --baseline single_agent \
        --metrics ndcg@5,recall@5,mrr,answer_score --out comparison.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------- statistics


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a: float, b: float, x: float, itmax: int = 200, eps: float = 3e-12) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - _log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(b * math.log(1.0 - x) + a * math.log(x) - _log_beta(b, a)) * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: int) -> float:
    """Two-tailed survival function for Student's t."""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    return betainc(df / 2.0, 0.5, x)


def paired_t_test(a: Sequence[float], b: Sequence[float]) -> Dict[str, float]:
    """Paired two-tailed t-test on a - b."""
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    if n < 2:
        return {"n": n, "mean_diff": (diffs[0] if diffs else 0.0),
                "t": float("nan"), "p": float("nan"), "df": max(n - 1, 0)}
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    if var == 0.0:
        p = 0.0 if mean != 0.0 else 1.0
        return {"n": n, "mean_diff": mean, "t": float("inf") if mean else 0.0,
                "p": p, "df": n - 1}
    se = math.sqrt(var / n)
    t = mean / se
    return {"n": n, "mean_diff": mean, "t": t, "p": t_sf(t, n - 1), "df": n - 1}


def paired_bootstrap(a: Sequence[float], b: Sequence[float],
                     iters: int = 10000, seed: int = 42) -> Dict[str, float]:
    """Bootstrap the mean paired difference. Returns CI and a two-sided p.

    The p-value is the proportion of resamples whose mean difference falls on
    the opposite side of zero from the observed one, doubled.

    The tail count uses the add-one (Davison & Hinkley) estimator
    (count + 1) / (iters + 1) rather than the raw proportion. A raw proportion
    is exactly 0.0 whenever no resample crosses zero, which then prints as
    "<0.001" and survives Holm untouched -- claiming more evidence than
    `iters` resamples can support. With `iters=10000` the floor is p ~= 2e-4.
    """
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    if n == 0:
        return {"mean_diff": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p": float("nan")}
    observed = sum(diffs) / n
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        s = sum(diffs[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(0.025 * iters)]
    hi = means[min(int(0.975 * iters), iters - 1)]
    if observed >= 0:
        crossings = sum(1 for m in means if m <= 0.0)
    else:
        crossings = sum(1 for m in means if m >= 0.0)
    tail = (crossings + 1) / (iters + 1)
    return {"mean_diff": observed, "ci_low": lo, "ci_high": hi,
            "p": min(1.0, 2.0 * tail)}


def win_tie_loss(a: Sequence[float], b: Sequence[float],
                 eps: float = 1e-9) -> Tuple[int, int, int]:
    w = sum(1 for x, y in zip(a, b) if x - y > eps)
    l = sum(1 for x, y in zip(a, b) if y - x > eps)
    return w, len(a) - w - l, l


def holm(pvalues: Sequence[float]) -> List[float]:
    """Holm-Bonferroni step-down adjustment. NaNs pass through untouched."""
    idx = [i for i, p in enumerate(pvalues) if not math.isnan(p)]
    m = len(idx)
    out = list(pvalues)
    if m == 0:
        return out
    order = sorted(idx, key=lambda i: pvalues[i])
    running = 0.0
    for rank, i in enumerate(order):
        adj = (m - rank) * pvalues[i]
        running = max(running, min(1.0, adj))
        out[i] = running
    return out


# ------------------------------------------------------------ data plumbing

def load_per_query(run_dir: str) -> List[dict]:
    path = os.path.join(run_dir, "per_query.jsonl")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no per_query.jsonl in {run_dir}")
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _metric_value(row: dict, metric: str) -> Optional[float]:
    """Pull a metric out of a per_query row.

    Looks in `ir` first, then `answer_scores`, then top-level (latency_s,
    self_quality, n_docs).
    """
    ir = row.get("ir") or {}
    if metric in ir and ir[metric] is not None:
        return float(ir[metric])
    ans = row.get("answer_scores") or {}
    if metric in ans and ans[metric] is not None:
        try:
            return float(ans[metric])
        except (TypeError, ValueError):
            return None
    if metric in row and isinstance(row.get(metric), (int, float)):
        return float(row[metric])
    return None


def build_matrix(rows: Sequence[dict], metric: str) -> Dict[str, Dict[object, float]]:
    """{system: {query_id: value}} for one metric."""
    out: Dict[str, Dict[object, float]] = {}
    for r in rows:
        v = _metric_value(r, metric)
        if v is None:
            continue
        out.setdefault(r["system"], {})[r["query_id"]] = v
    return out


def paired_vectors(matrix: Dict[str, Dict[object, float]],
                   sys_a: str, sys_b: str) -> Tuple[List[float], List[float]]:
    """Values for the questions BOTH systems scored — never compare on
    different question subsets."""
    ids = sorted(set(matrix.get(sys_a, {})) & set(matrix.get(sys_b, {})), key=str)
    return ([matrix[sys_a][i] for i in ids],
            [matrix[sys_b][i] for i in ids])


def compare_metric(rows: Sequence[dict], metric: str, baseline: str,
                   bootstrap_iters: int = 10000, seed: int = 42) -> List[dict]:
    matrix = build_matrix(rows, metric)
    if baseline not in matrix:
        return []
    results = []
    for name in sorted(matrix):
        if name == baseline:
            continue
        a, b = paired_vectors(matrix, name, baseline)
        if not a:
            continue
        tt = paired_t_test(a, b)
        bs = paired_bootstrap(a, b, iters=bootstrap_iters, seed=seed)
        w, t_, l = win_tie_loss(a, b)
        results.append({
            "metric": metric, "system": name, "baseline": baseline,
            "n": len(a),
            "mean_system": sum(a) / len(a),
            "mean_baseline": sum(b) / len(b),
            "mean_diff": bs["mean_diff"],
            "ci_low": bs["ci_low"], "ci_high": bs["ci_high"],
            "p_ttest": tt["p"], "p_bootstrap": bs["p"],
            "wins": w, "ties": t_, "losses": l,
        })
    adjusted = holm([r["p_bootstrap"] for r in results])
    for r, p in zip(results, adjusted):
        r["p_holm"] = p
    return results


# --------------------------------------------------------------- reporting

def _fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "n/a"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def render_markdown(all_results: Sequence[dict], baseline: str,
                    run_dir: str) -> str:
    lines = [
        "# Head-to-head comparison",
        "",
        f"Baseline: `{baseline}`  ·  Run: `{os.path.basename(run_dir)}`",
        "",
        "Paired over the questions both systems answered. `Δ` is the mean paired "
        "difference (system − baseline); the CI and bootstrap p-value are from "
        "10k paired resamples. `p (Holm)` corrects across all comparisons in "
        "this table. W/T/L counts how many individual questions the system won, "
        "tied, and lost — a large Δ with a poor W/T/L means a few outliers are "
        "carrying the mean.",
        "",
    ]
    by_metric: Dict[str, List[dict]] = {}
    for r in all_results:
        by_metric.setdefault(r["metric"], []).append(r)

    for metric, rows in by_metric.items():
        lines += [f"## {metric}", "",
                  "| System | n | Mean | Baseline | Δ | 95% CI | p (t) | p (boot) | p (Holm) | W/T/L |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda x: -x["mean_diff"]):
            lines.append(
                f"| `{r['system']}` | {r['n']} | {r['mean_system']:.3f} | "
                f"{r['mean_baseline']:.3f} | {r['mean_diff']:+.3f} | "
                f"[{r['ci_low']:+.3f}, {r['ci_high']:+.3f}] | "
                f"{_fmt_p(r['p_ttest'])} | {_fmt_p(r['p_bootstrap'])} | "
                f"{_fmt_p(r['p_holm'])} | {r['wins']}/{r['ties']}/{r['losses']} |"
            )
        lines.append("")

    lines += [
        "## Reading this table",
        "",
        "A difference is worth reporting when the CI excludes zero *and* the "
        "Holm-corrected p-value stays below the threshold *and* the win/loss "
        "split is lopsided in the same direction. If those three disagree, the "
        "honest summary is that the evidence is mixed.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Paired head-to-head comparison of evaluated systems")
    p.add_argument("run_dir", help="results/<run_id> directory produced by run_eval")
    p.add_argument("--baseline", default="single_agent",
                   help="system to compare everything against (default: single_agent)")
    p.add_argument("--metrics", default="ndcg@5,recall@5,mrr,correctness,faithfulness,answer_relevance",
                   help="comma-separated metric names")
    p.add_argument("--bootstrap", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="comparison.md",
                   help="output filename, written inside run_dir")
    a = p.parse_args()

    rows = load_per_query(a.run_dir)
    systems = sorted({r["system"] for r in rows})
    print(f"[compare] systems in run: {', '.join(systems)}")
    if a.baseline not in systems:
        raise SystemExit(f"baseline {a.baseline!r} not in run; available: {systems}")

    all_results: List[dict] = []
    for metric in [m.strip() for m in a.metrics.split(",") if m.strip()]:
        res = compare_metric(rows, metric, a.baseline,
                             bootstrap_iters=a.bootstrap, seed=a.seed)
        if not res:
            print(f"[compare] no data for metric {metric!r} — skipped")
            continue
        all_results.extend(res)
        for r in res:
            print(f"  {metric:14s} {r['system']:24s} Δ={r['mean_diff']:+.3f} "
                  f"p_holm={_fmt_p(r['p_holm'])} W/T/L={r['wins']}/{r['ties']}/{r['losses']}")

    md = render_markdown(all_results, a.baseline, a.run_dir)
    out_path = os.path.join(a.run_dir, a.out)
    with open(out_path, "w") as f:
        f.write(md)
    json.dump(all_results, open(os.path.join(a.run_dir, "comparison.json"), "w"), indent=2)
    print(f"\n[compare] wrote {out_path}")


if __name__ == "__main__":
    main()
