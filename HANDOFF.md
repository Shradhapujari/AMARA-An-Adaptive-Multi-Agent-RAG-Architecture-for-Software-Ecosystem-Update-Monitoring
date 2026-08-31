# Handoff — current state

Working notes for picking this up in a fresh session. Findings and their
evidence live in [`eval_harness/FINDINGS.md`](eval_harness/FINDINGS.md); this
file is only *where things stand and what to do next*.

Last updated: 2026-08-31. Branch: `feat/llm-source-full`.

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

Current output: **34 pages** of the 45 permitted, zero undefined references or
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

1. **Read the typeset PDF.** It compiles; nobody has read the output
   front-to-back. After this much surgery the real risk is that it reads as a
   repaired conference paper rather than one argument.
2. **Voice.** §4's older subsections (Answer Accuracy, Representative Questions,
   Failure Analysis, Implementation Comparison, Qualitative Analysis) are
   conference-version prose. They no longer contradict anything, but they read
   unevenly against the rewritten sections.
3. **Journal-first eligibility.** Confirm the AgenticSE '26 workshop proceedings
   status satisfies TOSEM's journal-first rules.
4. **No head-to-head baseline results.** §2 defends the omission and now also
   states that a reimplementation of the mechanisms ships with the harness with
   no results reported. A reviewer may still press. Finishing that run (command
   below) is the cheapest answer; RAGLAB's `selfrag_llama3-8B` would be the
   stronger one but needs ~60 GB RAM for its ColBERT server against this
   machine's 24 GB.

### Numbers currently in the paper

| Claim | Value | Source |
|---|---|---|
| Bespoke retrieval score | 0.680 → 0.798 (+17.2%, *p*=0.020) | conference version, n=50 |
| Standard IR metrics, same systems | marag nDCG@3 0.145 vs baseline 0.765 | n=10 |
| Fetch-time loss, before fix | 22 of 23 relevant documents never retrieved | n=10 |
| Ranking ablation, single-phrasing | none 0.145 / bm25 0.212 / embed 0.188 | n=10 |
| Union fetch | nDCG@3 **0.765** (post-keyfix), MRR 1.000 | n=10 |
| Union, rank on rewrite vs original | 0.597 vs 0.621 — not established | n=10, n=9 |
| Scaled evaluation | marag 0.859 vs baseline 0.863 | n=100 |
| Fetch-time loss, after fix | 19 of 158 (12.0%), pool-based | n=100 |
| Faithfulness, format confound | template 0.700, prose 0.926, baseline 0.931 | n=100 |
| Second sample (reverses nominal order) | marag 0.781 vs baseline 0.768 | n=100, 28 GT |
| Correctness | 0.296 / 0.367 / 0.326 — all wrong more often than right | n=24–27 |

Every row maps to a run id in [`results/PROVENANCE.md`](results/PROVENANCE.md),
which also marks which runs predate the qrels-cache key fix.

Two numbers that were wrong earlier and are worth not reintroducing: **0.973**
was a pre-keyfix artifact (post-fix, reproducibly, 0.765), and the scaled tables
were once reported at n=96 from a stalled run that has since completed at n=100.

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

Sanity check: `./venv311/bin/python -m pytest tests/ -q` → **399 passing**,
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
| substring boost, single-phrasing | 0.145 | 0.250 |
| `bm25`, single-phrasing | 0.212 | 0.500 |
| `embed`, single-phrasing | 0.188 | 0.625 |
| `embed` + union fetch | **0.765** | **1.000** |

Note which change is the lever. Once both phrasings are retrieved, even the
original substring boost reaches 0.597; ranking against the original question
rather than the rewrite adds 0.024 on top (0.621 vs 0.597), which is not
established at this sample size. The reranking work came first and matters least
— adopt the union first.

This reaches **parity** with the single-agent baseline, not superiority, at
roughly 2× latency. The multi-agent justification is therefore
still unproven — that is the open research question, not a code problem.

### Stopped deliberately (2026-08-31)

Work was halted here to finalize the paper. Three things are complete as code but
have no results in the paper, by choice:

- **The self-reflective baseline arm** (`eval_harness/selfreflective.py`,
  `--generators selfreflective`). A reimplementation of Self-RAG's per-passage
  critiques and CRAG's corrective flow over our retrieval, model held constant.
  43 tests. Its evaluation run was stopped at 8 of 100 questions; no results are
  reported, and Section 2 says so explicitly rather than leaving the arm
  unmentioned. To finish it:
  `MARAG_RERANK=embed python -m eval_harness.run_eval --dataset data/benchmark_100.json --generators selfreflective,single_agent:ollama:llama3.1,marag:ollama:llama3.1 --judge ollama:llama3.1`
  (~85 min at ~52 s/question for three arms). Per-query rows carry
  `critique_trace`, so `n_retrieved - n_relevant` gives the count of documents
  the critic discarded.
- **Two ISREL bugs, both fixed**, both found by a peer session reading the code
  against its own comments: the relevance critique failed *closed* on a
  malformed reply, and a negated rejection ("not irrelevant") was read as a
  rejection. Both sat on the side that narrows the candidate set toward the
  critic's preferences, which is the circularity the threats section discusses.
  The bound the paper needs — a document is discarded only when the critique
  asserts IRRELEVANT as a non-negated word — now holds, pinned by 28 tests.
- **Three sessions worked this repo concurrently.** By Claude-Session trailer:
  `0186v` (paper's scaled tables, the self-reflective arm, this file,
  PROVENANCE.md, compile plumbing), `01SCr` (inversion statistics,
  judge-independence threat, judge bibitems), `01T8t` (`scripts/phase_*.sh` --
  the top_k sweep, phase ablation, qwen check, frozen-corpus control). If a
  change looks like it appeared from nowhere, check `git log` before assuming a
  bug. Note that `phase_ablation.sh` and a queued resume share an identical
  `--generators marag,single_agent --judge-pool` signature, so a pattern-based
  process gate cannot tell them apart -- only the corpus directory or parent pid
  can.

### Previously in flight

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
