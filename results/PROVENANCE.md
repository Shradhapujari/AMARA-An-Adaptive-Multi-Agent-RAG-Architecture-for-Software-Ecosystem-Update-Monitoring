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

## Table 6 — the ground-truth sample

All cells from `run_1788160859_67177cd53aab`, n=100, post-fix.

- Dataset: `data/benchmark_100.json` (28 reference answers, selected to prefer
  ground-truth records within each ecosystem-by-category cell)
- Generators and reranker as above; judge `ollama:llama3.1`
- This run shared the machine with other work, so its absolute latencies are
  inflated; only the within-run ratio is meaningful.

This is an independent sample of the same comparison. Its nominal ordering on
retrieval, faithfulness and correctness is the reverse of Tables 4 and 5, with
overlapping intervals throughout — which is the paper's evidence that no
difference is being measured.

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

## The ablation ladder (grounding vs coordination)

Two runs, same 100 questions, same eight arms. **Cite the frozen one.**

| Run | Corpus | n | Cache | Role |
|---|---|---|---|---|
| `run_1788319745_67177cd53aab` | `record:results/corpus_ladder_20260901`, `frozen=false`, 12,680 responses recorded | 100 | post-fix | recording pass, live fetches |
| `run_1788422938_67177cd53aab` | `replay:results/corpus_ladder_20260901`, `frozen=true`, 12,344 hits / 240 misses, **0 on document hosts** | 100 | post-fix | **the citable run** |

- Dataset: `data/benchmark_100.json`; seed 42; `top_k=4`
- Reranker: `embed:nomic-embed-text`; judge: `ollama:qwen2.5:7b-instruct`
- Generators: `raw:ollama:mistral`, `single_agent:ollama:mistral`,
  `single_agent_grounded:ollama:mistral`, `rewrite_only:ollama:mistral`,
  `marag:ollama:mistral`, `marag_retry:ollama:mistral`, `marag`,
  `single_agent_template` — synthesis model held at `mistral` on every arm that
  makes an LLM call, and the judge wrote none of the answers.

Only the replay run served every arm byte-identical documents; the recording
run fetched live and its arms hit the feeds hours apart, which is the same
not-strictly-paired caveat as item 1 above. The replay reproduces the recording
run's conclusions to three decimals, so the pair is reported together and the
frozen run is the one quoted.

Headline results, paired Wilcoxon on per-question differences (frozen run):

| Comparison | Metric | Mean delta | Better / worse | p |
|---|---|---|---|---|
| A1 -> A1g (grounding) | nDCG@3 | +0.049 | 14 / 5 | 0.0070 |
| A1 -> A1g | Recall@3 | +0.051 | 12 / 4 | 0.0035 |
| A1 -> A1g | nDCG@5 | +0.042 | 15 / 9 | 0.0268 |
| A1 -> A3 (coordination) | nDCG@5 | +0.018 | 9 / 10 | 0.8721 |
| A1 -> A3 | Recall@5 | +0.007 | 6 / 8 | 1.0000 |
| A1g vs A3 | nDCG@5 | -0.024 | 12 / 20 | 0.2172 |

Four things this run establishes that the numbers alone do not say:

1. **`mrr` and `ndcg@1` are null for A1 -> A1g**, not significant, despite
   nominal p of 0.0431 and 0.1088. Those come from 5 and 3 non-zero pairs, where
   the smallest two-sided p the signed-rank test can attain is 0.0625 and 0.25 —
   the normal approximation reported a value below the attainable floor. Same
   failure mode as the n=10 inversion in Table 1.
2. **Rung A4 measures nothing on this benchmark.** `marag_llm_retry` returned
   identical documents *and* identical answers to `marag_llm` on 100 of 100
   questions. Retry fires below self-quality 0.15; the minimum observed was
   0.300. Report it as a rung that had no opportunity to act, not as a rung with
   no effect.
3. **Rung A2 is the reason A3 looks like progress.** `rewrite_only` scores
   nDCG@5 0.231 against the baseline's 0.742; `marag_llm` adds union fetch and
   returns to 0.761, level with the baseline. Union fetch repairs the damage
   rewriting does rather than improving on single-agent retrieval, and omitting
   A2 from the ladder hides that.
4. **Template rendering costs about 0.10 faithfulness**, in both cells of the
   2x2 and with the tightest intervals in the run: `marag_llm` -> `marag`
   -0.095 (51 worse / 19 better) and `single_agent` ->
   `single_agent_template` -0.102 (52 worse / 13 better), both p < 0.0001. Any
   template-versus-prose comparison measures this before it measures retrieval.

Two limits on what these runs can be compared against:

- **Retrieval numbers collected before commit `ed206a2` (2026-09-01) are void**
  for any product with an active CVE feed. `fetch_vendor_releases` cut its
  candidate list to `limit` before the `canonical_score` sort ran, so shipped
  releases were unreachable — measured, 0 shipped releases in 40 retrieved
  documents for `q=linux`. Both arms shared that retriever, so the direction of
  earlier comparisons likely holds while the absolute values do not.
- **The A1g arm was corrected mid-measurement.** Its first version retrieved on
  the bare product name and scored *below* the baseline it exists to improve;
  the version measured here retrieves on products plus content terms
  (commit `08cbcc2`). A partial run of the earlier arm exists at
  `run_1788315588_67177cd53aab` (11 questions) and is not reportable.

Latency is not comparable across arms in either run: the recording pass ran
overnight on a laptop that entered clamshell sleep, so its wall-clock times
include suspend, and the replay pass reports sub-second times because documents
and model responses both come from cache.

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
