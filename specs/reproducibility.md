# Reproducibility — artifact packaging and ACM badges

Executed by Phase 7 of `specs/roadmap.md`.

---

## 1. Badges we are aiming at

ACM's badging scheme has two independent axes. Aim at all three of the following;
the third is the one this project's design is built around.

| Badge | What it requires | Our route |
|---|---|---|
| **Artifacts Available** | Artifacts permanently archived with a DOI | Zenodo deposit of the repository at the submission tag, plus the headline corpus snapshot |
| **Artifacts Evaluated — Functional** | Documented, consistent, complete, exercisable | `README.md` clean-clone steps; `pytest` suite; a two-question smoke run |
| **Results Reproduced** | An independent party obtains the headline results | The frozen corpus makes this possible without live-API luck |

Without the corpus snapshot, "Results Reproduced" is unattainable by construction:
the sources drift, and a reviewer running the pipeline next month would query a
different corpus. `corpus_snapshot.py` is the artifact feature that makes the badge
reachable, so ship the snapshot, not just the code.

## 2. What gets archived

| Item | Size | Notes |
|---|---|---|
| Repository at the submission tag | small | Excludes `venv311/`, `results/`, snapshots |
| Headline corpus snapshot | ~1.3 MB per question, so ~400 MB at n=300 | Gzipped per-request records; the thing that makes replay work |
| Headline `results/<run_id>/` directories | small | `config.json`, `per_query.jsonl`, `qrels.json`, `aggregate.csv`, `report.md`, plots |
| `results/qrels_cache.json` | small | The judgments; lets a reviewer skip re-judging |
| `pip freeze` and `ollama list` output | tiny | Captured at run time, not reconstructed later |

`results/` and `data/corpus_snapshot*/` are gitignored on purpose — they are large and
regenerable — so archiving them is a deliberate, separate step, not something git does
for you. Do not let the gitignore silently drop the artifact.

## 3. Clean-clone rehearsal

Run this on a machine that has never built the project. Write the outcome up as
`docs/reproduction-check.md`, including anything that went wrong.

```bash
git clone <repo> && cd Adaptive-Multi-Agent-RAG-...
python3.11 -m venv venv311
./venv311/bin/pip install -r requirements.txt

ollama serve &
ollama pull llama3.1 && ollama pull mistral && ollama pull nomic-embed-text

./venv311/bin/python -m pytest tests eval_harness -q     # expect green

# unpack the archived snapshot into data/corpus_snapshot_headline/, then:
MARAG_RERANK=embed ./venv311/bin/python -m eval_harness.run_eval \
  --dataset data/benchmark_300.json --generators marag,single_agent \
  --judge ollama:llama3.1 --judge-pool \
  --corpus replay:data/corpus_snapshot_headline
```

**Pass condition.** The run reports `corpus.frozen == true` with zero corpus-host
misses, and `aggregate.csv` matches the published table within the reported CIs.

**If retrieval metrics differ at all**, the freeze leaked — check
`corpus.misses_by_host` before suspecting anything else. Answer metrics may differ
slightly if the judge's sampling is not fully deterministic; retrieval metrics should
not, because they depend only on the documents and the shipped qrels.

## 4. Determinism, honestly stated

| Layer | Deterministic under replay? | Why |
|---|---|---|
| Source documents | Yes | Byte-identical recorded responses |
| Query rewrite | Yes | `call_llama` goes through `urlopen`, so it is snapshotted |
| BM25 ranking | Yes | Pure Python, no model |
| `none` ranking | Yes | Pure string matching |
| Embedding ranking | Yes for recorded prompts | Novel prompts miss and go live; misses are counted |
| Answer synthesis | Yes for recorded prompts | Same caveat |
| LLM judging | Cached | `qrels_cache.json` reuse; judgments were stable across three runs (0/60 flips) |

The honest summary for the paper: **retrieval metrics are exactly reproducible from
the archived snapshot; answer metrics are reproducible to within judge variation,
which we bound by shipping the judgment cache.**

## 5. Artifact appendix content

- One-paragraph description of what the artifact contains.
- Hardware and software requirements, from `specs/tech-stack.md`.
- Estimated run time per experiment, stated per phase — the n=300 record pass is
  hours, not minutes, and a reviewer should know before starting.
- Exact commands, copy-pasteable, matching `evaluation-protocol.md` §7.
- The DOI.
- A note that the demo UIs (`app.py`, `DemoMain*.py`, `marag_app.py`) are not part of
  the evaluated artifact and carry no claims.
