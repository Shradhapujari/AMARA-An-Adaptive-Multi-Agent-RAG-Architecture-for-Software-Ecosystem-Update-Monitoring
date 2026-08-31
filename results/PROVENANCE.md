# Provenance — which run produced which number

Every number in `paper/tosem_amara.tex` and the run that produced it. The paper
claims the ablation arms are released; this file is what makes that claim
checkable.

Two caveats apply throughout and are stated in the paper:

1. **Live sources.** Every run retrieves from live APIs whose contents change.
   A given run is reproducible from its own saved `qrels.json` and
   `per_query.jsonl`; two runs made hours apart are not strictly paired.
2. **The qrels cache key fix.** Relevance judgments were originally cached by a
   question's row position, so datasets with overlapping ids could read each
   other's labels. Runs made before the fix are marked **pre-fix** below and
   should not be mixed with post-fix runs in a controlled comparison. A run
   directory containing `qrels_cache_snapshot.json` is post-fix.

## Table 1 — the metric inversion

| Row | Run | Cache |
|---|---|---|
| Bespoke score, both systems (n=50) | conference version; not re-run here | — |
| nDCG@1 / nDCG@3 / MRR, both systems (n=10) | `run_1788128243_237950e265eb` | pre-fix |

## Table 3 — ranking and retrieval ablation

Panel (a), single-phrasing retrieval, n=10:

| Ranking function | Run | Cache |
|---|---|---|
| Substring boost | `run_1788128243_237950e265eb` | pre-fix |
| Okapi BM25 | `run_1788128704_237950e265eb` | pre-fix |
| Embedding cosine | `run_1788129232_237950e265eb` | pre-fix |

Panel (b), union retrieval:

| Configuration | Run | Cache | n |
|---|---|---|---|
| Substring boost, rewritten query | `run_1788147304_237950e265eb` | post-fix | 10 |
| Substring boost, original question | `run_1788148035_237950e265eb` | post-fix | 9 |
| Embedding cosine, original question | `run_1788133873_237950e265eb` | post-fix | 10 |

The embedding row was originally reported as nDCG@3 0.973 from
`run_1788129818_237950e265eb` (pre-fix). Re-measured post-fix it is 0.765,
reproduced independently by `run_1788135008_237950e265eb`. The paper reports
0.765.

**Panel (b) is not a fully controlled ablation.** Its three rows come from
separate runs against live sources, and the reranker and the ranked phrasing vary
across them. The panel (a) → (b) contrast is large enough to survive that; the
within-panel (b) differences are not, and the paper says so.

## Tables 4 and 5 — the scaled evaluation

All cells from `run_1788139377_6a8e9993db65`, n=100, post-fix.

- Dataset: `data/benchmark_300.json`, `--limit 100 --stratify category,ecosystem`
- Generators: `marag`, `marag:ollama:llama3.1` (reported as `marag_llm`),
  `single_agent:ollama:llama3.1` — synthesis model held constant
- Reranker: `MARAG_RERANK=embed`; ranked phrasing: original question
- Judge: `ollama:llama3.1`

This run stalled at question 98 and was later completed. Numbers reported in an
earlier draft as n=96 were hand-computed from `per_query.jsonl` mid-run; the
paper now uses the completed n=100 artifact.

## Fetch-time loss

Both figures are the same measurement: the share of the baseline's
judge-labelled relevant documents absent from the multi-agent **candidate pool**
(not its top-k).

| Figure | Set | Run |
|---|---|---|
| 22 of 23 (96%) | 10 ground-truth questions | `run_1788128704_237950e265eb` |
| 19 of 158 (12.0%) | 100-question benchmark subset | `run_1788139377_6a8e9993db65` |

A top-k version of the second figure gives 23 of 158 (14.6%). An earlier draft
reported that number against the pool-based 96%, which mixed definitions.

## Reproducing an arm

```bash
MARAG_RERANK=none|bm25|embed \
MARAG_RANK_QUERY=original|rewritten \
python -m eval_harness.run_eval \
    --dataset validation_gt.json --generators marag,single_agent \
    --judge ollama:llama3.1
```

`MARAG_RERANK=none` with `MARAG_RANK_QUERY=rewritten` is the configuration the
conference version shipped.
