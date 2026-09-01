# Evaluation and Findings

The evidence chain, in the order it happened: a defect was measured,
misdiagnosed once, then correctly diagnosed and fixed. The superseded reading is
kept because the sequence is itself the evidence.

The authoritative version lives in `eval_harness/FINDINGS.md` in the repository,
and every number maps to a run id in `results/PROVENANCE.md`.

---

## 1. The published result

| Measure | Value |
|---|---|
| Bespoke keyword-overlap "quality" score | 0.680 → 0.798 |
| Improvement over the single-agent baseline | **+17.2%** |
| Paired *t*-test | *t*(49) = 2.32, *p* = 0.020, n = 50 |

Every component behaved correctly. The metric its designers watched moved the
right way.

## 2. Re-scored with standard IR metrics, the ordering inverts

n = 10 ground-truth set (`validation_gt.json`), judge `ollama:llama3.1`, seed 42.

| System | nDCG@1 | nDCG@3 | MRR | Faithfulness |
|---|---:|---:|---:|---:|
| Single-agent baseline | **0.800** | **0.743** | **0.800** | **0.805** |
| Multi-agent, as published | 0.167 | 0.193 | 0.433 | 0.660 |

Paired deficit on nDCG@3: **0.620**, exact Wilcoxon *p* = 0.016 — which is the
smallest *p* attainable with seven nonzero pairs, so report it as the floor
rather than as a precise level.

## 3. First diagnosis: the rewriter degrades retrieval

Isolating the rewriter (same retriever, raw versus rewritten query, same qrels —
`python -m eval_harness.diagnose_rewriter`):

| | raw query | rewritten query |
|---|---:|---:|
| Mean nDCG@3 | **0.743** | 0.193 |
| helped / hurt / tie | — | **0 / 7 / 3** |

The measurement holds. The *explanation* was incomplete: it pointed at ranking.

## 4. Fixing ranking is not sufficient

| Ranking arm | marag nDCG@3 | marag MRR |
|---|---:|---:|
| `none` (published behaviour) | 0.145 | 0.250 |
| `bm25` | 0.212 | 0.500 |
| `embed` | 0.188 | 0.625 |

**Rising MRR under stronger rerankers with a flat nDCG is the signature of a
fetch fault, not a ranking one.** Reranking cannot promote a document that was
never retrieved.

## 5. The actual defect

The rewritten query *replaced* the user's wording at every live endpoint, so
**22 of the 23** relevant documents the baseline retrieved were never fetched at
all.

| Configuration | nDCG@3 | MRR |
|---|---:|---:|
| `embed`, single phrasing | 0.188 | 0.625 |
| `embed` + **union fetch** | **0.765** | **1.000** |

Note which change is the lever. Once both phrasings are fetched, even the
original substring boost reaches 0.597; ranking against the original question
adds 0.024 on top (0.621 versus 0.597), which is **not established** at this
sample size. The reranking work came first and mattered least — adopt the union
first.

## 6. At scale (n = 100)

| Measure | Value |
|---|---|
| Baseline-relevant documents missing from the candidate pool | 96% → **12%** |
| nDCG@3, multi-agent vs baseline, synthesis model held constant | 0.859 vs 0.863 |
| Latency per question | ≈ 23 s vs ≈ 12 s |

That is **parity, not superiority**, at roughly twice the cost. Decomposition
per se is not what produced the original +17.2%. A second 100-question sample
reverses the nominal order (0.781 vs 0.768), which is the honest way to read a
difference this small.

## 7. A confound that was not retrieval at all

An apparent 0.23 faithfulness deficit for the multi-agent system:

| Arm | Faithfulness |
|---|---:|
| Multi-agent, template answer | 0.700 |
| Multi-agent, prose answer (baseline's own prompt) | 0.926 |
| Single-agent baseline, prose answer | **0.931** |

Same retrieval, same model, different **rendering**. A structured template
judged against fluent prose scores lower for reasons that have nothing to do
with grounding. Hold the answer format constant, or you are scoring formatting.

## 8. Correctness is low for everyone

Deterministic CRAG-style labelling gives 0.296 / 0.367 / 0.326 across the arms
(n = 24–27): every system is wrong more often than right on this task. That is a
statement about the difficulty of the domain, not a ranking of the systems.

---

## Numbers not to reintroduce

- **nDCG@3 0.973** — a pre-qrels-cache-keyfix artifact. Post-fix and
  reproducibly, the same configuration scores **0.765**.
- **Scaled tables at n = 96** — a stalled run that has since completed at
  **n = 100**.
- **+9.3% self-improvement** — stated without its caveat. It compares
  time-ordered tertiles against a corpus that drifts during the run, so
  adaptation is not separable from drift.

## What is deliberately not claimed

A reimplementation of Self-RAG-style per-passage critiques and CRAG-style
correction over this retrieval ships in `eval_harness/selfreflective.py`, with
the model held constant and 43 tests behind it. Its evaluation run stopped at 8
of 100 questions, so **no results are reported from it** — the paper says so
explicitly rather than leaving the arm unmentioned.

The 300-question run is likewise incomplete; it stopped at 68 of 300 and
`--resume` exists to continue it.

---

## Reproducing any of this

```bash
# the 10-question ground truth, all arms
MARAG_RERANK=embed python -m eval_harness.run_eval \
    --dataset validation_gt.json --generators marag,single_agent

# ranking ablation
for arm in none bm25 embed; do
  MARAG_RERANK=$arm python -m eval_harness.run_eval \
      --dataset validation_gt.json --generators marag,single_agent
done

# paired statistics over a completed run
python -m eval_harness.compare results/<run_id> --baseline single_agent \
    --metrics ndcg@5,recall@5,mrr,answer_score
```

`compare.py` reports a bootstrap 95% CI, a paired *t*-test, a non-parametric
bootstrap *p*, Holm correction across the family, and win/tie/loss counts. Treat
a difference as real only when the CI excludes zero, the corrected *p* holds,
**and** the win/loss split points the same way.
