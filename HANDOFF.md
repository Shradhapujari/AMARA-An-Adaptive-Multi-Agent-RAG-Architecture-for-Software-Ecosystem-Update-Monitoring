# Handoff — current state

Working notes for picking this up in a fresh session. Findings and their
evidence live in [`eval_harness/FINDINGS.md`](eval_harness/FINDINGS.md); this
file is only *where things stand and what to do next*.

Last updated: 2026-08-30. Branch: `feat/llm-source-full`.

---

## The paper is the active work

**Deadline: 1 September 2026** — TOSEM special section on Human-AI Collaboration
in Software Engineering, journal-first / fast-impact track, up to 45 pages.
Submit at <https://mc.manuscriptcentral.com/tosem>, submission type "Human AI
Collaboration in Software Engineering".

Source: **`paper/tosem_amara.tex`** (derived from `~/Downloads/paper_7.tex`, the
AgenticSE '26 conference version, retargeted to `acmsmall`).

**It compiles.** `tectonic` is installed (`brew install tectonic` — a formula, so
no sudo, unlike the BasicTeX cask). Build with:

```bash
tectonic -X compile paper/tosem_amara.tex
```

Current output: **33 pages** of the 45 permitted, zero undefined references or
citations, two sub-visible overfull boxes (6pt and 11pt). Build products are
gitignored.

Do not trust a word-count estimate of the page count: 16,200 words came out as
33 pages, not the ~23 a 700-words-per-page estimate predicted, because the
tables, tikz figures and bibliography are not words.

`paper/Figures/execution-trace.png` is committed so the source is
self-contained. The original lives in `~/Downloads/tosem-overleaf/figures/` under
a different name (`execution-trace` vs the `execution_trace` the tex referenced),
which was a hard compile failure until fixed.

The paper is reframed around a negative result plus remedy. Section by section:
introduction and abstract state the finding; §2 positions it against prior work
on expansion drift; §3 documents the retrieval design; §4 reports the evidence
chain; §5 and §6 argue what generalizes. Fragments used to build it
(`paper/frag_*.tex`) are kept for reference and are already spliced in — do not
splice them twice.

### Before submitting

1. **Compile it.** Never typeset. Expect the usual first-compile fixes.
2. **Voice.** §4's older subsections (Answer Accuracy, Representative Questions,
   Failure Analysis, Implementation Comparison, Qualitative Analysis) are
   conference-version prose. They no longer contradict anything, but they read
   unevenly against the rewritten sections.
3. **Journal-first eligibility.** Confirm the AgenticSE '26 workshop proceedings
   status satisfies TOSEM's journal-first rules.
4. **No head-to-head baseline was run.** §2 defends the omission (Self-RAG needs
   a static Contriever/Wikipedia index; CRAG needs a fine-tuned T5-large
   evaluator plus per-dataset thresholds). A reviewer may still press. RAGLAB
   ships `selfrag_llama3-8B` and would be the cheapest way to answer it.

### Numbers currently in the paper

| Claim | Value | Source |
|---|---|---|
| Bespoke retrieval score | 0.680 → 0.798 (+17.2%, *p*=0.020) | conference version, n=50 |
| Standard IR metrics, same systems | marag nDCG@3 0.145 vs baseline 0.765 | n=10 |
| Fetch-time loss, before fix | 22 of 23 relevant documents never retrieved | n=10 |
| Ranking ablation | none 0.145 / bm25 0.212 / embed 0.188 | n=10 |
| Union fetch | nDCG@3 0.973, MRR 1.000 | n=10 |
| Scaled evaluation | marag 0.865 [0.80,0.92] vs baseline 0.869 [0.81,0.92] | n=96 |
| Fetch-time loss, after fix | 14.7% (23 of 156) | n=96 |
| Faithfulness, format confound | template 0.702, prose 0.924, baseline 0.929 | n=96 |
| Latency | 19.6 s vs 9.5 s median | n=96 |

The n=96 numbers come from `results/run_1788139377_6a8e9993db65`. That run
stopped at question 98 of 100 without writing `report.md`; the aggregates were
computed directly from `per_query.jsonl`. `--resume` on that run id would
finish it and produce the official artifact.

**Caveat carried in the paper:** the 9.3% self-improvement figure compares
time-ordered tertiles against a live corpus that drifts during a run, so
adaptation is not separable from drift. Reported as mechanism-sound,
magnitude-unestablished. Fixing it needs a frozen snapshot (`MARAG_CORPUS=record:<dir>`
then `replay:<dir>`) or an interleaved design.

---

## Environment

There is no committed virtualenv. Recreate:

```bash
python3.11 -m venv venv311
./venv311/bin/pip install requests ollama numpy matplotlib pytest
ollama pull llama3.1          # generation + judge
ollama pull nomic-embed-text  # embedding reranker
```

The harness itself needs only `requests` plus the stdlib — LangChain,
smolagents, FAISS and ChromaDB in `requirements.txt` belong to the Streamlit
app and the alternative implementations, not to `eval_harness/`.

Sanity check: `./venv311/bin/python -m pytest tests/ -q` → **267 passing**,
offline, no network.

---

## Where the work stands

### Settled

The published +17.2% retrieval gain does not hold under standard IR metrics.
Two real defects were found, fixed and regression-tested:

1. **Ranking** — the retriever ordered candidates by a substring boost over the
   first four tokens of the *rewritten* query, which after a rewrite are filler.
   Ranking now scores against the original question via `rerank.py`
   (`MARAG_RERANK=none|bm25|embed`, `none` reproduces the published behaviour
   and is kept as the ablation arm).
2. **Fetching** — the rewrite *replaced* the user's wording at every live
   endpoint, so **22 of 23** relevant documents the baseline retrieved were
   never fetched at all. Both phrasings are now searched and the pools unioned.

Effect on the 10-question ground-truth set (`validation_gt.json`):

| Configuration | marag nDCG@3 | marag MRR |
|---|---:|---:|
| published | 0.145 | 0.250 |
| `bm25` | 0.212 | 0.500 |
| `embed` | 0.188 | 0.625 |
| `embed` + union fetch | **0.973** | **1.000** |

This reaches **parity** with the single-agent baseline (0.988), not
superiority, at roughly 2× latency. The multi-agent justification is therefore
still unproven — that is the open research question, not a code problem.

### In flight

**The 300-question run is incomplete.** It died at question **68 of 300**.
`--resume` exists for this. To continue:

```bash
MARAG_RERANK=embed ./venv311/bin/python -m eval_harness.run_eval \
    --dataset data/benchmark_300.json \
    --generators marag,marag:ollama:mistral,single_agent \
    --judge ollama:llama3.1 --resume <run_id>
```

Find `<run_id>` under `results/`. Note the arms in that run hold **Mistral**
constant across `marag_llm` and `single_agent`; `marag` is the template-answer
arm. Expect several hours — roughly 60s per question across three arms.

For a faster read, `--limit` is now safe: `--stratify category,ecosystem`
balances both dimensions and a smaller limit is a strict prefix of a larger
one, so a limited run can still be resumed upward.

---

## Open items, in the order they block the paper

1. **Finish the 300-question run.** n=10 cannot support any claim in either
   direction; every number above is directional only.
2. **Independent judge.** The judge (`ollama:llama3.1`) shares a model family
   with the system under test. Set `OPENAI_API_KEY` and pass
   `--judge openai:gpt-4o`. This is the single most likely reviewer objection.
3. **Head-to-head against published systems.** Researched, not started:
   - **RAGLAB** — ships a fine-tuned `selfrag_llama3-8B` checkpoint plus VLLM
     and 4-bit configs, so Self-RAG runs on this hardware without retraining.
     Also carries a standalone query-rewrite pipeline, i.e. a ready-made
     rewrite-helps-or-hurts ablation.
   - **FlashRAG** (MIT) — 23 algorithms in one harness including Self-RAG,
     Adaptive-RAG and FLARE.
   - Self-RAG direct assumes a static Contriever/Wikipedia index (~100 GB RAM);
     CRAG direct needs a fine-tuned T5-large evaluator and two per-dataset
     thresholds re-tuned. Both are expensive ports — prefer the harnesses.
4. **Paper §4 and §5.** Blocked on (1) and (2). The retrieval-quality table and
   the multi-agent justification both need rewriting against whatever the
   300-question run says.

---

## Traps worth knowing

- **The qrels cache used to be keyed by row position.** Datasets with
  overlapping ids read each other's relevance labels. Fixed (keys are a hash of
  the question text) and old entries are dropped on load, but any results
  directory produced before that fix is suspect. `results/qrels_cache.pre-keyfix.bak`
  is the pre-fix cache, kept only as a record.
- **`single_agent` is unaffected by the union-fetch change** — it passes the
  same string as original and rewritten, so the union collapses to one search.
  That is what makes the before/after a clean comparison for the multi-agent arm.
- **A bare `single_agent` synthesises with Mistral** while `marag` uses
  Llama 3.1. Retrieval metrics are model-independent; answer metrics are not.
  Hold the model constant explicitly: `single_agent:ollama:llama3.1`.
- **`marag`'s answer is a template** assembled by `EvaluatorAgent`, not model
  prose. An LLM judge comparing it against `single_agent` partly measures
  format. Use the `marag:<backend>:<model>` spec (reported as `marag_llm`) for
  answer-quality comparisons.
- **Live APIs drift.** A given run is reproducible through its saved qrels and
  per-query documents; two runs days apart are not strictly comparable. Snapshot
  the pool if strict comparability is needed.
- **`data/.benchmark_cache/`** is ~111 MB of raw API responses and is
  deliberately git-ignored by a `.gitignore` inside itself. Rebuild with
  `python build_multiecosystem_benchmark.py --refresh`; replay offline with
  `--offline`.
- **Two sessions edited this repo concurrently** on 2026-08-30. If something
  looks like it changed under you, check `git log` before assuming a bug.
