# Evaluation Findings

Results from the Tier-1 harness (`eval_harness/`) on the 10 ground-truth
validation questions (`validation_gt.json`), judge `ollama:llama3.1`, seed 42.
Reproduce: see `eval_harness/README.md`. Numbers are auditable in
`results/<run_id>/` (per_query.jsonl, qrels.json).

> ⚠️ Sample size is small (n=10) with wide, overlapping confidence intervals.
> These are directional findings. The 300-question multi-ecosystem set
> (`data/benchmark_300.json`) exists to test them at a size that can support a
> claim, and a stronger independent judge is still needed
> (`--judge openai:gpt-4o` with an API key set).

This file reads in order: a defect was measured, misdiagnosed once, then
correctly diagnosed and fixed. The superseded findings are kept because the
sequence is the evidence.

---

## Finding 1 — The published retrieval gain does not survive standard IR metrics

| System | nDCG@1 | nDCG@3 | MRR | faithfulness |
|---|---:|---:|---:|---:|
| single_agent (raw query) | **0.800** | **0.743** | **0.800** | **0.805** |
| marag (multi-agent)      | 0.167 | 0.193 | 0.433 | 0.660 |

This **inverts the paper's headline**. The paper's number was measured on a
bespoke keyword-overlap "quality" score, not a standard IR metric. Under
Recall@k / nDCG@k / MRR with judged relevance, the multi-agent pipeline lost.

**Status: confirmed, and the cause is now known — see Findings 3 and 4.**

---

## Finding 2 — First diagnosis: the Query Rewriter degrades retrieval

Isolating the rewriter (same retriever, raw vs rewritten query, same qrels —
`python -m eval_harness.diagnose_rewriter`):

| | raw query | rewritten query |
|---|---:|---:|
| Mean nDCG@3 | **0.743** | 0.193 |
| Rewrite helped / hurt / tie | — | **0 / 7 / 3** |

The rewriter helped **0 of 10** queries and hurt **7**.

| Raw query | Rewrite | nDCG@3 raw → rw |
|---|---|---|
| `G6 Bullet unstable?` | `"Unstable behavior in G6 Bullet software: …"` | 0.879 → 0.242 |
| `Queue limitations - hard limit of 200` | `"Queue capacity threshold - does setting a…"` | 1.000 → 0.000 |
| `I can't run Ace-Step 1.5 XL on Comfy!?` | `"Are there any known issues or updates for…"` | 1.000 → 0.000 |

**Status: the measurement holds; the explanation was incomplete.** The original
reading — that the retriever's lexical matching mismatches the rewrite's formal
vocabulary — pointed at *ranking*. Fixing ranking alone recovered only part of
the loss (Finding 3), which is what exposed the real cause (Finding 4).

---

## Finding 3 — Fixing the ranking stage is not sufficient

The retriever's final ordering was a substring boost over the first four tokens
of the *rewritten* query — tokens which, after a rewrite, are filler. Replacing
it with a reranker scored against the **original** question (`rerank.py`, arms
selected by `MARAG_RERANK`) gives:

| Ranking arm | marag nDCG@3 | marag MRR | single_agent nDCG@3 | single_agent MRR |
|---|---:|---:|---:|---:|
| `none` (published behaviour) | 0.145 | 0.250 | 0.765 | 0.800 |
| `bm25` | 0.212 | 0.500 | 0.891 | 1.000 |
| `embed` (nomic-embed-text) | 0.188 | 0.625 | 0.984 | 1.000 |

marag's MRR improves monotonically with a better reranker, confirming ranking
*was* broken. But the gap does not close: the baseline improves at least as
much, because both systems share the reranker.

**Reading it:** if better ranking cannot close the gap, the missing documents
are not being mis-ranked. They are not there.

---

## Finding 4 — The loss is at fetch time: the rewrite *replaced* the user's query

Counting, per question, how many of the relevant documents the baseline
retrieved were present anywhere in marag's candidate pool (arm `bm25`):

> **22 of 23** relevant documents that single_agent retrieved were never
> fetched by marag at all.

Every live endpoint was being queried with the rewritten string only. The
documents that match what the user actually asked never entered the pool, so no
reranker could promote them. marag *did* find relevant documents the baseline
missed — the rewrite has real recall value — they were simply a different,
smaller set.

**Fix:** the rewrite augments the search rather than substituting for it. Both
phrasings are searched and the pools unioned, deduped by URL
(`RetrieverAgent.run`, `dedupe_docs`).

| Configuration | marag nDCG@3 | marag MRR | marag recall@5 |
|---|---:|---:|---:|
| `embed`, rewrite replaces query | 0.188 | 0.625 | 0.327 |
| `embed`, rewrite augments query | **0.973** | **1.000** | **0.933** |

---

## Finding 5 — With both fixes, multi-agent *matches* the baseline; it does not beat it

| System | nDCG@3 | recall@5 | faithfulness | latency |
|---|---:|---:|---:|---:|
| marag (`embed` + union fetch) | 0.973 | 0.933 | 0.705 | 23.1s |
| single_agent | 0.988 | 1.000 | 0.865 | 12.0s |

The retrieval difference sits well inside the confidence intervals. On this
set, the multi-agent pipeline costs roughly 2× the latency to reach parity.

**The claim that multi-agent decomposition improves retrieval is not supported
at n=10.** What is supported: the architecture had two real defects, both now
fixed and both regression-tested.

Note that `single_agent` is unaffected by the union-fetch change — it passes the
same string as original and rewritten, so the union collapses to one search.
The comparison is therefore a clean before/after for the multi-agent arm only.

---

## Confounds, and what has been done about them

| Confound | Status |
|---|---|
| **Answer format.** marag's answer is a template assembled by `EvaluatorAgent`; single_agent's is model prose. An LLM judge scoring these against each other measures format as much as content, so the faithfulness gap above is not yet evidence of anything. | Addressed: the `marag:<backend>:<model>` spec runs the same multi-agent retrieval with the answer synthesised by a named model through the shared prompt, reported as `marag_llm`. |
| **Synthesis model.** A bare `single_agent` synthesises with Mistral while marag uses Llama 3.1, though the paper reports Llama 3.1 throughout. Retrieval metrics are model-independent and unaffected; answer metrics were confounded. | Addressed by holding the model constant: `--generators marag,marag:ollama:llama3.1,single_agent:ollama:llama3.1`. |
| **Judge independence.** The judge (`ollama:llama3.1`) shares a model family with the system under test. | Open. Needs a stronger independent judge before publication. |
| **Qrels cache collisions.** The relevance cache was keyed by a question's *row position*, so datasets with overlapping ids read each other's labels. Runs made before this fix shared a cache with `table_50` runs. | Fixed (keys are now a hash of the question text); old-format entries are dropped rather than trusted. Headline numbers are being re-measured against a regenerated cache. |
| **Live APIs.** The document pool drifts, so a *given run* is reproducible via its saved qrels and per-query docs, but two runs days apart are not strictly comparable. | Open by design. A frozen snapshot is the fix if strict comparability is needed. |

---

## What this means for the paper

1. The +17.2% retrieval claim cannot stand as written — it rests on a bespoke
   metric that standard IR metrics contradict.
2. There is a genuine, publishable finding underneath: **query rewriting that
   replaces the user's query destroys retrieval, and the damage is at fetch
   time, not ranking time.** It is measured, mechanistically explained, and
   fixed. Prior work motivates rewriting for recall; this is a concrete failure
   mode and a cheap remedy.
3. The multi-agent justification needs different evidence than retrieval
   parity. The 300-question set is the place to look for it.

## Reproducing

```bash
# ranking ablation
for arm in none bm25 embed; do
  MARAG_RERANK=$arm python -m eval_harness.run_eval \
    --dataset validation_gt.json --generators marag,single_agent
done

# model held constant, answer-format confound removed
MARAG_RERANK=embed python -m eval_harness.run_eval \
  --dataset validation_gt.json \
  --generators marag,marag:ollama:llama3.1,single_agent:ollama:llama3.1 \
  --judge ollama:llama3.1

# the fetch-time diagnosis of Finding 4
python -m eval_harness.diagnose_rewriter
```
