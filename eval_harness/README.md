# Multi-Agent RAG System Evaluation Harness (Tier 1)

A reproducible, **benchmark-grounded, model-comparative** evaluation for the
Multi-Agent RAG System multi-agent RAG system. It replaces the paper's bespoke "retrieval
quality" heuristic with the metrics reviewers actually expect, and runs the
same questions through multiple systems and models head-to-head.

## Why this exists

Conference / poster feedback that this directly answers:

| Feedback | What the harness does |
|---|---|
| "Evaluate answers with **benchmarks**" | Standard IR metrics: **Recall@k, nDCG@k, MRR** over LLM-judged relevance, plus RAGAS-style **faithfulness / answer-relevance / correctness** |
| "Compare with **other models** (GPT, Gemini, Grok)" | Provider-agnostic generators — run Multi-Agent RAG System vs single-agent vs raw GPT/Claude/Llama/Mistral in one table |
| "Why **multi-agent** / does it help?" | Run `marag` vs `single_agent` side by side (the ablation) |
| "**Result tables and graphs**" | Auto-generated markdown + CSV tables and matplotlib bar charts with 95% CIs |
| "**Reproducibility / transparency of data**" | Frozen dataset hash, seed, cached & saved qrels, full per-query JSONL, config manifest |

## Install / run

Use the project's Python 3.11 environment (the Multi-Agent RAG System module needs 3.10+):

```bash
venv311/bin/python -m eval_harness.run_eval \
  --dataset validation_gt.json \
  --generators marag,single_agent,raw:ollama:llama3.1,raw:ollama:mistral \
  --judge ollama:llama3.1
```

Requires **Ollama running** locally (`llama3.1`, `mistral` pulled). Add an
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to your environment and the GPT/Claude
generators light up automatically — **no code change**:

```bash
export OPENAI_API_KEY=sk-...
venv311/bin/python -m eval_harness.run_eval --generators marag,raw:openai:gpt-4o
```

## Generator specs

| Spec | System |
|---|---|
| `marag` | Full 4-agent pipeline (Rewriter → Retriever → RLAIF Evaluator); answer is the Evaluator's template |
| `marag:ollama:mistral` | Same pipeline, answer synthesised by that model through the shared prompt — reported as `marag_llm` |
| `rewrite_only:ollama:mistral` | Rewriting **without** the two-phrasing union fetch, prose answer — one rung below `marag_llm` |
| `marag_retry:ollama:mistral` | `marag_llm` **plus** ManagerAgent's adaptive retry — reported as `marag_llm_retry` |
| `marag_retry` | Same retry loop, template answer |
| `single_agent` | Paper's baseline: raw query → keyword retrieval → 1 LLM call |
| `single_agent_template` | Baseline retrieval, EvaluatorAgent template answer — the fourth cell of the rendering × retrieval factorial (no LLM call) |
| `single_agent:openai:gpt-4o` | Baseline with a chosen synthesis model |
| `raw:ollama:llama3.1` | No retrieval — model answers directly (model-comparison column) |
| `raw:openai:gpt-4o` | Same, GPT-4o (needs key) |
| `raw:anthropic:claude-sonnet-4-6` | Same, Claude (needs key) |

### Which arm to compare against the baseline

`marag`'s answer is a template (headers, bullets, source tags); `single_agent`'s
is LLM prose. An LLM judge scoring those two against each other measures answer
*format* alongside content, so `marag` vs `single_agent` **answer** metrics are
confounded — their retrieval metrics are not, since the retrieval path is
identical in both arms.

For an answer-quality claim, run the synthesising arm against the baseline with
the same model on both sides:

```bash
venv311/bin/python -m eval_harness.run_eval \
  --generators marag:ollama:mistral,single_agent \
  --judge ollama:llama3.1
```

Both sides then use the identical prompt (`generators.build_synthesis_prompt`)
and the identical model, so what remains between them is the retrieval
pipeline. The judge stays a model that wrote neither answer. `per_query.jsonl`
records `synth_model` and the `template_answer` that was set aside, so the
published system's own output is still auditable.

## The ablation ladder, and why the arms are not "different tasks"

A reviewer looking at a capability table sees the multi-agent arm holding
capabilities the baseline lacks, and asks whether the two arms are even doing
the same task. Two answers, and they are different in kind:

**Capabilities that *are* the treatment** — query rewriting, union fetch,
adaptive retry — must differ; they are the independent variable. The defence is
that everything else is pinned: same corpus, same `RetrieverAgent`, same
`top_k`, same synthesis model, same `build_synthesis_prompt`, same judge, same
questions, paired within run. The baseline is an ablation of the coordination
layer, not a different system.

**Capabilities that are *not* the treatment but leak into measurement** — the
answer rendering, and the pipeline's own retrieval score — are confounds, and
have to be neutralised rather than defended.

The ladder turns the first group into single-factor comparisons. Each adjacent
pair differs by exactly one capability:

| Rung | Spec | Adds |
|---|---|---|
| A0 | `raw:ollama:mistral` | — (no retrieval) |
| A1 | `single_agent` | retrieval on the raw question, prose answer |
| A2 | `rewrite_only:ollama:mistral` | LLM query rewriting |
| A3 | `marag:ollama:mistral` (`marag_llm`) | union fetch over both phrasings |
| A4 | `marag_retry:ollama:mistral` | adaptive retry on a negative RLAIF signal |
| A5 | `marag` | template rendering |

A3 also runs the RLAIF Evaluator, but in a prose arm the Evaluator's output is
only `self_quality` — it does not touch the answer or the documents — so A2→A3
is the union-fetch effect alone.

And the rendering confound becomes a **2×2 factorial** rather than an inference
across two arms:

|  | prose | template |
|---|---|---|
| baseline retrieval | `single_agent` | `single_agent_template` |
| multi-agent retrieval | `marag_llm` | `marag` |

All four cells now exist, so rendering and retrieval are estimable as main
effects with an interaction term. `single_agent_template` makes no LLM call —
it is deterministic and effectively free to add to any run.

```bash
venv311/bin/python -m eval_harness.run_eval \
  --dataset data/benchmark_100.json \
  --generators single_agent,single_agent_template,rewrite_only:ollama:mistral,marag:ollama:mistral,marag_retry:ollama:mistral,marag \
  --judge ollama:qwen2.5:7b-instruct --corpus strict:results/<record-dir>
```

### Two capabilities the table claims and the harness cannot test

- **Adaptive retry fires at quality < 0.15, not θ = 0.30.** `EvaluatorAgent`
  emits `"⚠️ negative — manager will retry"` below 0.15; 0.30 is a separate
  constant in that method, a quality *floor* for tier-1 and Apple sources.
  Also: `MultiAgentRAGGenerator` never called `ManagerAgent`, so **no published
  measurement of this pipeline included the orchestrator or its retry** until
  the `marag_retry` arm above. Report it as an added rung, not as a property of
  the numbers already collected.
- **Persistent term-weight memory is not in the evaluated system at all.**
  `self_improving_agent.py` is a standalone demo over a 12-document hardcoded
  list; nothing imports it, and it does not touch `RetrieverAgent` or the live
  endpoints. It cannot appear as a ladder rung without being ported first —
  which is new work, not an ablation. Until then it belongs in future work, not
  in a capability column of the results.
- **The bespoke keyword-overlap score (the "17.2%") is not an evaluation
  metric.** It is `EvaluatorAgent`'s internal control signal — the same number
  that gates the retry — and the baseline has no counterpart by construction.
  Scoring the two arms with it means grading the treatment with its own ruler.
  It belongs in the mechanism description, not in the results.

### One statistical hazard if memory is ever added

Term-weight learning makes question *n* depend on questions 1..*n*−1, so the
per-question differences stop being exchangeable and the paired tests in
`compare.py` no longer apply as written. Either reset the memory per question
(and report it as ablated, not tested) or fix the question order, report it, and
treat that rung as a sequential-dependence result.

## Output

Each run writes `results/<run_id>/`:

- `report.md` — head-to-head + per-category tables
- `aggregate.csv` — same numbers, machine-readable
- `plot_retrieval.png`, `plot_answer.png` — bar charts with error bars
- `per_query.jsonl` — every system's answer + scores per question (audit trail)
- `qrels.json` — the relevance judgments used (auditable, cached & reused)
- `config.json` — full run manifest (dataset hash, seed, models, judge)

## Known limitations (honest notes)

- **Judge independence.** With only local models, the judge can overlap with a
  system under test (e.g. `raw:ollama:llama3.1` judged by `ollama:llama3.1`).
  For publication, use a stronger independent judge (set an API key and
  `--judge openai:gpt-4o`). This is flagged because the conference panels
  stressed provider independence in evaluation.
- **Ground-truth coverage.** `correctness` is only computed where the dataset
  provides a reference answer (e.g. `validation_gt.json`). IR metrics depend on
  judged relevance, not gold qrels — pooled & cached, but judge-derived.
- **Live APIs.** Multi-Agent RAG System retrieves from releasetrain.io live APIs, so the
  document pool can drift over time. The qrels cache + saved per-query docs
  make a *given run* reproducible; for a fully frozen corpus, snapshot the pool.
```
