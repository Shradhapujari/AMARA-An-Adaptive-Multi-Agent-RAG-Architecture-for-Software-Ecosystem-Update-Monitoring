# Runs of record for the paper

`results/` is gitignored (see `.gitignore`), so these are the artifacts a reader
needs to re-derive the paper's retrieval numbers from the repository alone. Only
the files a claim depends on are kept — `per_query.jsonl`, `config.json`,
`qrels.json`, `aggregate.csv`. The plot PNGs and per-run qrels-cache snapshots are
omitted: the first are regenerable, the second are redundant with the shipped
`results/qrels_cache.json`.

`scripts/inversion_stats.py` and `scripts/paper_figures.py` read `results/` when
it is present and fall back to this directory when it is not, so both work in a
fresh clone.

| Run | Backs |
|---|---|
| `run_1788128243_237950e265eb` | Table 2 (the inversion), Figure 2, and the exact paired statistics. Ablation panel (a), substring boost. |
| `run_1788128704_237950e265eb` | Ablation panel (a), Okapi BM25. The 22-of-23 document census. |
| `run_1788129232_237950e265eb` | Ablation panel (a), embedding cosine. |
| `run_1788147304_237950e265eb` | Ablation panel (b), substring boost ranked against the rewritten query. |
| `run_1788148035_237950e265eb` | Ablation panel (b), substring boost ranked against the original question. Nine questions, not ten — hence the `n <= 10` in the table caption. |
| `run_1788133873_237950e265eb` | Ablation panel (b), embedding cosine ranked against the original question. |
| `run_1788139377_6a8e9993db65` | Table 4 and Table 5, the first 100-question stratified sample. |
| `run_1788160859_67177cd53aab` | Table 6, the second 100-question selection. |

## Reading these honestly

Two properties are recorded in the configs and matter when reusing the numbers.

`corpus.mode` is `live` for `run_1788139377` and `run_1788160859`, with
`frozen: false`. Neither carries a frozen-corpus claim; they are independent draws
against sources that change between runs.

`judge_pool` is a *widening* flag, not a pooling switch. Cross-system pooling is
unconditional in `run_eval.py` — the judged set is always the union of every
system's returned documents, with one shared label set per question.
`--judge-pool` additionally admits the pre-rerank candidates, which is what makes
`pool_recall` meaningful; without it the field is `None` rather than a
tautological 1.0.

Latency columns from contended runs are not comparable. Several of these ran while
other evaluations shared the GPU.
