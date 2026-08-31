# Mission — Adaptive Multi-Agent RAG for Software Ecosystem Update Monitoring

> One question about a software update → sources fetched across vendor, community and
> vulnerability feeds → one answer with an evidence chain → every number in the paper
> re-derivable from a saved run directory.

Target venue: an ACM journal (see `specs/writing.md` for the submission plan and the
artifact badges we are aiming at).

---

## 1. Problem

An engineer asking "is Firefox 149 safe to roll out?" has to consult sources that do
not talk to each other: vendor release notes, changelogs, CISA KEV, CVE records,
vendor subreddits, news. Each has a different shape, a different update cadence, and a
different notion of what counts as an answer. The information exists; assembling it
per question does not scale.

Retrieval-augmented generation is the obvious tool, and the obvious first move is to
rewrite the user's shorthand question into document vocabulary before searching. That
move is where this project found its result.

## 2. What we build

A multi-agent RAG pipeline (`multiagent_rag_v3.py`) over live software-ecosystem
sources, plus an evaluation harness (`eval_harness/`) built to standard IR metrics
rather than a bespoke score. Three agents:

1. **Query Rewriter** — Llama 3.1 turns shorthand into document vocabulary.
2. **Retriever** — fans out across vendor, community, and vulnerability sources,
   then reranks the candidate pool.
3. **Evaluator** — RLAIF-style self-scoring plus answer assembly.

The baseline it is measured against, `single_agent`, is the same retriever fed the raw
question with no rewriting, no reranking choice, and one synthesis call.

## 3. Claims, and what would falsify each

The claims are stated so that a reviewer can see what evidence would kill them. This
section is the contract the rest of the repository serves.

| # | Claim | Falsified by |
|---|---|---|
| **C1** | A query rewrite that *replaces* the user's question destroys retrieval, and the damage is at fetch time, not ranking time. | Showing that a strong reranker over the replace-mode pool recovers baseline nDCG — i.e. the documents were present and merely mis-ordered. |
| **C2** | Making the rewrite *augment* the search (union of both phrasings) repairs the damage at negligible cost. | Union fetch failing to recover nDCG@3, or costing latency//token budget out of proportion to the gain. |
| **C3** | Multi-agent decomposition, once both defects are fixed, reaches parity with a single-agent baseline on retrieval — it does not beat it. | A frozen-corpus run at adequate n where marag beats single_agent on nDCG@3 / recall@5 outside the confidence interval. |
| **C4** | Standard IR metrics contradict the bespoke keyword-overlap "quality" score the original write-up reported. | Showing the bespoke score and nDCG/MRR agree on ranking of systems under judged relevance. |

**C1 and C2 are the paper.** C3 is an honest negative result that gives C1/C2 their
context. C4 is a methodological note, not a headline.

What we are explicitly **not** claiming: that this architecture is state of the art,
that multi-agent decomposition is generally superior, or that the +17.2 % retrieval
improvement in the original draft stands. It does not.

## 4. Scope

**In scope**

- Live retrieval over releasetrain.io, CISA KEV, CVE, Apple RSS, Google News, Reddit.
- Locally hosted models via Ollama (llama3.1, mistral, nomic-embed-text).
- IR metrics with judged relevance: recall@k, precision@k, nDCG@k, MRR.
- LLM-judged answer metrics: faithfulness, answer relevance, correctness.
- Ablations over ranking backend (`MARAG_RERANK`) and fetch mode.
- A 300-question multi-ecosystem benchmark with per-record provenance.

**Out of scope**

- Serving traffic, latency SLOs, a production UI. The Streamlit apps in the repo root
  are demos, are not exercised by the harness, and carry no claims.
- Fine-tuning. Every model is used off the shelf.
- Closed-model dependence. An OpenAI judge is supported as a *stronger independent
  judge* option, not as a requirement to reproduce.

## 5. Success criteria

### Artifact

- [x] Every reported number traces to a `results/<run_id>/` directory containing
      `config.json`, `per_query.jsonl`, `qrels.json`, `aggregate.csv`.
- [x] `config.json` records which ablation arm actually ran, read off the live object
      rather than the environment (`rerank_spec`, `rerank_degraded`).
- [x] A degraded backend (embed silently falling back to BM25) can never be reported
      as the backend that was requested.
- [x] Retrieval nondeterminism is controllable: `MARAG_CORPUS=record:<dir>` then
      `replay:<dir>` freezes every source so arms differ only in the arm.
- [x] A run that read a document host live during replay is marked `frozen: false`
      and prints a warning.
- [x] The pre-rerank candidate pool is logged, so "buried by ranking" and "never
      fetched" are distinguishable from the artifacts alone.
- [ ] Pool recall is measured on the full ground-truth set with `--judge-pool`.
- [ ] The headline table is produced from a frozen-corpus run at the sample size the
      power analysis requires (`specs/evaluation-protocol.md` §6).
- [ ] An independent judge (not sharing a model family with any system under test)
      reproduces the ranking of the systems.
- [x] Test suite green, with a regression test for each fixed defect.

### Paper

- [ ] C1 supported by the pool-membership count, with the mechanism stated.
- [ ] C2 supported by a before/after on the same frozen corpus.
- [ ] C3 reported as a negative result with confidence intervals, not buried.
- [ ] Every threat in `specs/evaluation-protocol.md` §8 either closed or declared.
- [ ] Generative-AI use disclosed per ACM policy (`specs/writing.md` §4).
- [ ] Artifact submitted for ACM badging (`specs/reproducibility.md`).

## 6. Where the project actually stands

Honest status as of the current branch, so the roadmap starts from truth.

| Area | State |
|---|---|
| Pipeline | Both defects fixed: rewrite augments rather than replaces; ranking scores against the original question. |
| Headline result | C1/C2 supported at n=10. C3 supported at n=10. All three need the larger set. |
| Sample size | 10 questions. The power analysis says an effect worth reporting needs ~130–250 questions per arm; `data/benchmark_300.json` exists but has not carried a headline run. |
| Corpus stability | Fixed but unexercised — `corpus_snapshot.py` landed with tests; no headline run has used it yet. |
| Judge | `ollama:llama3.1`, same family as a system under test. Open threat. |
| Superseded numbers | The three-arm sweep of 2026-08-30 15:17–15:36 predates the fetch fix and must not be quoted. |

Read next: `specs/tech-stack.md` (with what) → `specs/pipeline.md` (how it is wired) →
`specs/evaluation-protocol.md` (how it is measured) → `specs/roadmap.md` (in what order).
