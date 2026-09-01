# Are the two arms doing the same task?

A reviewer looking at a capability table sees the multi-agent arm holding
capabilities the baseline lacks and asks the obvious question: if the two arms
do not have the same abilities, is the comparison measuring coordination, or is
it measuring the extra abilities?

The question is right, and the answer is not "defend the gap". It is to split
the capabilities in two and treat each half differently.

**Capabilities that _are_ the treatment must differ.** Union fetch, the
orchestrator, adaptive retry, template rendering — these are the independent
variable. A baseline that had them would not be a baseline.

**Capabilities that are _not_ the treatment must be equal in both arms.** Query
understanding is the clearest case. Resolving "today" to a date, recognising
that "Linux" names a catalog product, deciding whether a question is asking
about security or about a release — none of that is coordination. If it were
reachable only from the multi-agent pipeline, every measured gap would be the
sum of *coordination helps* and *understanding the question helps*, and the
paper claims only the first.

That is why the grounding added in this branch lives in
[`grounding.py`](../grounding.py) as one function both arms call, rather than
inside the multi-agent pipeline. Adding a capability to one arm only is how a
comparison stops being a comparison.

## The capability table, row by row

Status values:

- **shared** — both arms have it, pinned identical, not a factor
- **treatment** — the independent variable, isolated as one rung of the ladder
- **correction** — the row as stated does not match the code
- **not evaluated** — exists in the repo but is not in any measured arm

| Pipeline stage / capability | Table said | Status | Where it actually is |
|---|---|---|---|
| Receive user question | both | shared | — |
| Query rewriting | both | **correction** | The baseline uses the **raw** question. `SingleAgentGenerator.generate` passes `query` straight to the retriever ([generators.py](../eval_harness/generators.py)). Rewriting is rung **A2** (`rewrite_only`), so it is measured as a single factor, not held by both. |
| Vendor-aware retrieval (detection + vendor-scoped endpoints) | both | shared | Both arms construct the same `marag.RetrieverAgent()`. Now also available to both through `grounding.ground` → `vendor.detect_vendors`. |
| Document retrieval from live endpoints | both | shared | Same retriever, same endpoints, same corpus snapshot. |
| Union fetch — original and rewritten phrasing, merged | multi only | **treatment** | Rung **A2 → A3**. |
| Retrieval-quality scoring / evaluation | both | shared | The harness's IR metrics and judge score both arms identically. Distinct from the row below — this is the *measurement*, not a system component. |
| Bespoke keyword-overlap score (the "17.2%") | multi only | **correction** | Not an evaluation metric. It is `EvaluatorAgent`'s internal control signal, the same number that gates the retry. Scoring the arms with it means grading the treatment with its own ruler. It belongs in the mechanism description, not the results. |
| Dedicated orchestrator / coordinator | multi only | **treatment** | Rung **A3 → A4**. Note: `MultiAgentRAGGenerator` never called `ManagerAgent`, so no published number for this pipeline included the orchestrator until the `marag_retry` arm existed. |
| Adaptive retrieval retry (re-run when score < θ) | multi only, θ = 0.30 | **correction** | Fires below **0.15**, not 0.30. `EvaluatorAgent` emits `"negative — manager will retry"` under 0.15; 0.30 is a separate constant in the same method, a quality *floor* for tier-1 and Apple sources. |
| Persistent self-improvement memory (term-weight learning) | multi only | **not evaluated** | `self_improving_agent.py` is a standalone demo over a 12-document hardcoded list. Nothing imports it; it does not touch `RetrieverAgent` or the live endpoints. It cannot be a ladder rung without being ported first, which is new work rather than an ablation. |
| Reranking (none / BM25 / embedding) | both | shared | One reranker per run, selected by `MARAG_RERANK` and recorded in the run manifest (`rerank_spec`, `rerank_degraded`). Both arms get the same one. |
| Answer synthesis as prose via shared prompt | both | shared | Both call `build_synthesis_prompt` with the same model. |
| Answer synthesis as structured template | multi only | **treatment**, and a confound | Handled as a 2×2 rather than a difference: `single_agent_template` gives baseline retrieval with template rendering, so rendering and retrieval are estimable as main effects with an interaction term. |

## What this leaves

Four rows are genuine treatment: union fetch, the orchestrator, adaptive retry,
template rendering. The ablation ladder makes each adjacent pair differ by
exactly one of them:

| Rung | Spec | Adds |
|---|---|---|
| A0 | `raw:ollama:mistral` | — (no retrieval) |
| A1 | `single_agent` | retrieval on the raw question, prose answer |
| A2 | `rewrite_only:ollama:mistral` | LLM query rewriting |
| A3 | `marag:ollama:mistral` (`marag_llm`) | union fetch over both phrasings |
| A4 | `marag_retry:ollama:mistral` | adaptive retry on a negative RLAIF signal |
| A5 | `marag` | template rendering |

Three rows are corrections to the table rather than differences to defend, and
one row (memory) describes something that is not in any measured arm.

Everything else is pinned identical across arms: same corpus, same
`RetrieverAgent`, same `top_k`, same reranker, same synthesis model, same
synthesis prompt, same judge, same questions, paired within run.

## The rung this branch adds

The grounding layer is not coordination, so it does not belong to the
multi-agent arm. It belongs to a rung both arms can stand on:

| Rung | Spec | Adds |
|---|---|---|
| **A1g** | `single_agent_grounded` | temporal + vendor + intent grounding, baseline retrieval |

Two comparisons then become available, and they answer different questions:

- **A1 → A1g** — what does grounding the question buy, with no coordination at
  all? This is the honest home for the vendor/temporal/intent work.
- **A1g → A3g** — what does coordination buy *once both arms understand the
  question*? This is the multi-agent claim, with the grounding confound removed
  rather than argued away.

Reporting A1 → A3 without A1g would attribute the grounding gain to
coordination. That is precisely the objection the capability table raises, and
running the extra rung answers it with a number instead of a paragraph.

## A retriever bug the grounding exposed — and what it invalidates

Building the rung above surfaced a defect in the **shared** retriever, which
means it affected both arms equally and is not a comparability issue — but it
does change numbers.

`fetch_vendor_releases` in [`multiagent_rag_v3.py`](../multiagent_rag_v3.py)
ranks its rows with a `canonical_score` whose stated purpose is to demote CVE
rows and promote the canonical brand; its own comment says it "fixes Linux
returning openCryptoki instead of torvalds kernel". The sort was dead in
practice, because the list was cut to `limit` before it ran:

```python
releases = releases[:limit]          # 10 rows — all advisories
...
releases.sort(key=canonical_score)   # nothing left to promote
```

`/api/c/name/linux` returns its 449 CVE rows ahead of its 157 `torvalds`
release rows, because advisories are filed daily and kernels are not. So the
first ten were always advisories, and **the shipped kernel was unreachable**:
measured 2026-09-01, `RetrieverAgent` returned 0 shipped releases in 40
retrieved documents for `q=linux`.

Ranking now happens before the cut. After the fix, on the same query:

| | advisories in pool | shipped releases in pool |
|---|---|---|
| before | 10 | 0 |
| after | 2 | 1 |

and `single_agent_grounded` answers "What is the latest Linux version?" with
`v7.1.0` instead of declining or naming an advisory.

**This invalidates retrieval numbers collected before the fix** for any
question whose product has an active CVE feed. Both arms were affected
identically, so the *direction* of published comparisons is unlikely to move,
but the absolute IR metrics will. Runs reported after this commit must be
re-collected; runs reported before it should be cited with the commit that
produced them. `tests/test_vendor_release_ranking.py` pins the ordering, and
was confirmed to fail on the previous code.

## Why "make the tasks identical" has a limit

The tasks are already identical: same questions, same corpus, same judge. What
differs is the *system*, which is the point of an ablation. The failure mode
worth guarding against is not that the arms differ — it is that they differ in
more than one way at a time, so no single difference can be credited. Every row
above is therefore either pinned equal, or isolated as one rung, or removed
from the results as not-a-metric.

## See also

- [`eval_harness/README.md`](../eval_harness/README.md) — the ladder, the 2×2, and how to run them
- [`eval_harness/FINDINGS.md`](../eval_harness/FINDINGS.md) — the evidence chain
- [`Grounding-Before-After.md`](Grounding-Before-After.md) — what the grounding changes on live data
- [`results/PROVENANCE.md`](../results/PROVENANCE.md) — the run id behind every reported number
