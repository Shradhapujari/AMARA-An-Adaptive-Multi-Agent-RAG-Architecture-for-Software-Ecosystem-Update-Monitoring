# benchmark_100, three arms — results of record

What this directory is: the artifacts behind the retrieval and answer-format
findings, copied out of `results/` (which is not tracked) so the numbers in the
paper have a checkable source in the repository.

## Provenance

| | |
|---|---|
| dataset | `data/benchmark_100.json` (100 questions, hash `67177cd53aab`) |
| arms | `marag`, `single_agent` (run `1788146393`), `marag_llm` (run `1788160991`) |
| judge | `ollama:llama3.1`; robustness re-judged with `ollama:qwen2.5:7b-instruct` |
| synthesis | `marag_llm` and `single_agent` both `ollama:mistral`, identical prompt |

`marag_llm` was measured in its own run rather than the same one (a `--resume`
that did not take, fixed in `fa443c2`). Merging the two was **refused**: the
arms retrieved different documents on 10 of 100 questions, because
`--corpus replay:` fell through to the network in both runs — the target run's
config records `frozen: false` with 589 corpus misses served live. All analysis
below therefore runs on the **90 questions where the two multi-agent arms
retrieved the identical ranked documents**, with the dropped ids listed in
`format_confound.md`.

## Files

- `format_confound.md` — the decomposition: what is retrieval, what is format
- `judge_robustness.md` — the same contrast re-scored by an independent judge
- `report.md`, `aggregate.csv` — the two-arm head-to-head as the run produced it
  (`marag_llm` is not in these; it is folded in by the analysis scripts)
- `config.json`, `config.marag_llm_arm.json` — both runs' full manifests

## Reproducing

```bash
python analyze_format_confound.py results/run_1788146393_67177cd53aab \
    --extra-run results/run_1788160991_67177cd53aab --identical-only

python judge_robustness.py results/run_1788146393_67177cd53aab \
    --extra-run results/run_1788160991_67177cd53aab \
    --judge ollama:qwen2.5:7b-instruct --arms marag_llm,marag \
    --metric faithfulness --sample 40 --identical-retrieval
```

## What they show

The multi-agent pipeline's measured answer-quality deficit is its **answer
rendering**, not its retrieval. `marag` and `marag_llm` are the same pipeline
over the same documents in the same order; they differ only in that one emits a
~2000-character template and the other ~280 characters of prose from the same
sources.

| metric | format alone | retrieval + format | retrieval alone |
|---|---|---|---|
| faithfulness (n=90) | **+0.119** (p 6.5e-05) | −0.144 (p 2.6e-06) | −0.025 (p 0.098, n.s.) |
| correctness (n=17/18/16) | **+0.400** (p 0.0017) | −0.267 (p 0.0090) | +0.062 (p 0.16, n.s.) |

With the rendering matched, multi-agent and single-agent answer quality are
statistically indistinguishable, and retrieval was already indistinguishable
(mrr p=0.548, ndcg@5 p=0.378, 85–98 ties per 100 on the earlier 100-question
run).

The format effect is not an artefact of the judge that produced it:

| judge | Δ faithfulness | p | W/T/L |
|---|---|---|---|
| `ollama:llama3.1` (original) | +0.111 | 0.0122 | 21/11/8 |
| `ollama:qwen2.5:7b-instruct` (independent) | +0.107 | <0.0001 | 24/13/3 |

The independent judge is from a third model family — it drives neither the
Query Rewriter (llama3.1) nor the synthesis (mistral). It agrees with the
original on the aggregate level (mean faithfulness 0.796 vs 0.809) while
disagreeing question by question (29% exact), and the paired effect holds
under both.
