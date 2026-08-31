# Pipeline — execution graph, state, contracts, failure policy

The analogue of an execution graph for this project: what runs in what order, what
each stage is allowed to assume about its input, and what it must report about
itself. Contracts here are the interface between the pipeline and the harness;
changing one means editing this file in the same commit.

---

## 1. Graph

```
  user question q
        │
        ▼
  ┌───────────────────────┐
  │ A1  Query Rewriter    │  llama3.1, temperature 0
  │  q ──► q'             │  "rewrite to document vocabulary, <20 words"
  └───────────────────────┘
        │  {original: q, rewritten: q'}
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ A2  Retriever                                               │
  │                                                             │
  │  ── STEP 1/2  vendor detection ──► vendor_releases,         │
  │                                    vendor_reddit            │
  │                                                             │
  │  ── STEP 3  source fan-out, run for BOTH phrasings ──       │
  │      for s in [q', q]:            ◄── DEFECT 1 FIXED HERE   │
  │          releases, apple RSS, CISA KEV, CIRCL, CVE,         │
  │          LLM feed (gated), reddit, google news              │
  │                                                             │
  │  ── tiering ──                                              │
  │      tier1 = dedupe(vendor_releases + verified sources)     │
  │      tier2 = dedupe(vendor_reddit + community, seen=tier1)  │
  │      pool  = tier1 + tier2            ◄── LOGGED as `pool`  │
  │                                                             │
  │  ── ranking, per tier, against q NOT q' ──                  │
  │      MARAG_RERANK ∈ {none, bm25, embed} ◄ DEFECT 2 FIXED    │
  │      results = rank(tier1) + rank(tier2)                    │
  └─────────────────────────────────────────────────────────────┘
        │  results[:top_k]
        ▼
  ┌───────────────────────┐
  │ A3  Evaluator (RLAIF) │  self-scores retrieval quality,
  │                       │  assembles the template answer
  └───────────────────────┘
        │
        ▼
     answer + docs + self_quality
```

**Baseline (`single_agent`)** takes the same `RetrieverAgent` with `q` passed as both
the rewritten and the original query, so the union collapses to a single search, and
synthesises with one LLM call. It shares the reranker. That sharing is the reason
`single_agent` is **not** a rerank-independent control — see §5.

## 2. Why the graph looks like this — the two defects

Both are measured in `eval_harness/FINDINGS.md` and both carry regression tests.

**Defect 1 — the rewrite replaced the search string (fetch-time loss).**
Every live endpoint was queried with `q'` only. Counted on the 10-question set,
**22 of 23** relevant documents the baseline retrieved were never fetched by the
multi-agent arm at all. No reranker can promote a document that is not in the pool.
Fix: search both phrasings and union the pools, deduped by URL.

| Configuration | marag nDCG@3 | marag MRR | marag recall@5 |
|---|---:|---:|---:|
| `embed`, rewrite replaces query | 0.188 | 0.625 | 0.327 |
| `embed`, rewrite augments query | **0.973** | **1.000** | **0.933** |

**Defect 2 — ranking scored against the rewrite (ranking-time loss).**
Final ordering was a substring boost over the first four tokens of `q'`; after a
rewrite those tokens are filler. Fix: fetch with `q'` for recall, rank against `q` for
precision. `rerank.py` makes the backend an experimental variable rather than an
assumption, and keeps `none` as the arm that reproduces the original behaviour.

## 3. Data contracts

**Document** — what every source adapter must emit, and what the harness normalises.

```python
{"doc_id": str,     # sha1(url or title|source)[:12]  — stable, the qrels key
 "title": str, "text": str, "source": str, "url": str,
 "subreddit": str, "date": str}
```

`doc_id` is derived from the URL when present. Two sources surfacing the same URL are
one document; `dedupe_docs` relies on this, and so does every recall denominator.

**Generator output** — the contract between a system under test and the harness.

```python
{"answer": str,
 "docs": [doc, ...],          # ranked, cut to top_k
 "pool": [doc, ...],          # pre-rerank candidates; [] for retrieval-free arms
 "self_quality": float|None,
 "rerank_spec": str,          # the backend that actually ran
 "rerank_degraded": bool}     # true if it fell back
```

`pool` is the diagnostic that makes "buried by ranking" and "never fetched"
distinguishable from artifacts alone. Its absence is what made the 2026-08-30 sweep
un-analysable after the fact.

**Retriever diagnostics** — set on the agent instance by every `run()`:
`last_pool`, `last_rank_query`, `last_rerank_spec`, `last_rerank_degraded`.
Declared as class attributes so a caller can read them after an early return.

## 4. Failure and degradation policy

Retrieval must never take a run down, and a degradation must never be invisible.

| Failure | Behaviour | Reported as |
|---|---|---|
| Embedding backend unavailable at build time | Build BM25 instead | `spec = "bm25(fallback from embed:<model>)"`, `degraded = True` |
| Embedding call raises mid-run (timeout, reset) | Rank with BM25 for that call | printed warning; run continues |
| BM25 also raises | Keep the retriever's own order | printed warning |
| All live sources return nothing | Fall back to the local `DOCS` dataset | printed; answer header says "From local dataset" |
| Replay miss on a document host | Go live, record, count | `corpus_misses > 0`, `frozen: false`, WARNING printed |
| Replay miss on a model host | Go live, record, count | counted but does not void the run |
| Unknown `MARAG_RERANK` value | Raise | run aborts — a typo must not quietly measure the wrong arm |

The asymmetry in the last three rows is deliberate. A missing *document* voids a
cross-arm comparison; a missing *model call* does not, because arms legitimately make
different model calls — the embed arm queries an embeddings endpoint the `none` arm
never touches.

## 5. Controls, and the one we do not have

`single_agent` differs from `marag` in the rewrite and the answer path. It shares the
retriever, the source adapters, and the reranker. Therefore:

- It **is** a valid control for the rewrite (C1, C2). Union fetch collapses to a
  single search for it, so a before/after on union fetch is clean for the marag arm.
- It is **not** a control for the ranking backend. Both arms move when
  `MARAG_RERANK` changes, so a difference-in-differences across arms measures nothing.

The only control for corpus drift is `MARAG_CORPUS=replay:<dir>`. Without it, two runs
minutes apart returned a different document set on 10 of 10 questions for the same
question and the same system. Any cross-arm table built on live runs is void.

## 6. Cost model

Per question, arm `embed`, measured on the reference machine.

| Stage | Calls | Typical |
|---|---|---|
| Rewrite | 1 × llama3.1 | ~2 s |
| Source fan-out | ~8 endpoints × 2 phrasings | dominated by network |
| Reranking (`embed`) | 1 query + |pool| document embeddings, memoised per process | pool is 9–21 documents |
| Answer | 1 × llama3.1 (template arm does 0) | ~3 s |
| **marag total** | | **~20–23 s** |
| **single_agent total** | | **~12–17 s** |

Union fetch roughly doubles the fan-out. That cost is the price of C2 and belongs in
the paper next to the gain.
