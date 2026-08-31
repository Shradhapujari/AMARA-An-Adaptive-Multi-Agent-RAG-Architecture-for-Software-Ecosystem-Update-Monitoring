# Tech Stack — locked versions, endpoints, environment

Everything a third party needs to stand up the artifact and get the same numbers.
If a value here changes, the numbers may change: treat an edit to this file as a
result-affecting change and re-run the headline table.

---

## 1. Runtime

| Component | Version | Where |
|---|---|---|
| Python | 3.11.15 | `venv311/` (project-local; not the system 3.9 or 3.14) |
| Interpreter path | `./venv311/bin/python` | every command in this repo assumes it |
| OS used for reported numbers | macOS (darwin 25.5.0), Apple silicon | record any change in the paper's setup section |

There is no `uv`/Poetry workspace. The venv is created and installed from
`requirements.txt`.

```bash
python3.11 -m venv venv311
./venv311/bin/pip install -r requirements.txt
```

## 2. Python packages

Pinned in `requirements.txt`. Versions below are the ones present in `venv311` and
used for every number under `results/`.

| Package | Version | Used by |
|---|---|---|
| `requests` | 2.34.2 | every live source fetch in `multiagent_rag_v3.py` |
| `numpy` | 2.4.6 | metrics, plots |
| `pytest` | 9.1.1 | test suite (219 passed, 1 skipped at time of writing) |
| `matplotlib` | 3.11.1 | `eval_harness/report.py` plots |
| `streamlit` | `>=1.32.0`, **not installed in `venv311`** | demo UIs only (`app.py`, `DemoMain*.py`, `marag_app.py`); unverified, carries no claims |

Standard library only for the reranker (`rerank.py`) and the corpus snapshot
(`corpus_snapshot.py`) — deliberate, so the deterministic arm needs no model and no
third-party dependency to reproduce.

## 3. Models (Ollama, local)

Server: `http://localhost:11434`. All calls at `temperature=0`.

| Model | Role | Notes |
|---|---|---|
| `llama3.1:latest` | query rewriting; default LLM judge | Shares a family with a system under test — see the judge threat in `specs/evaluation-protocol.md` §8 |
| `mistral:latest` | default `single_agent` synthesis | Hold constant across arms when answer metrics are compared |
| `nomic-embed-text:latest` | `MARAG_RERANK=embed` backend | Falls back to BM25 if unavailable; the fallback is reported, never silent |
| `minimax-m2.7:cloud` | available, not used for reported numbers | If used, it stops being a fully local artifact — declare it |

```bash
ollama serve
ollama pull llama3.1 && ollama pull mistral && ollama pull nomic-embed-text
curl -s http://localhost:11434/api/tags        # readiness check
```

**Optional stronger judge.** `--judge openai:gpt-4o` with `OPENAI_API_KEY` set. Needed
to close the judge-independence threat; not needed to reproduce the retrieval metrics,
which are judge-dependent only through the qrels and are shipped in each run directory.

## 4. Live data sources

Read-only GETs. No credentials. These drift, which is why `corpus_snapshot.py` exists.

| Host | Endpoints | Feeds |
|---|---|---|
| `releasetrain.io` | `/api/v/`, `/api/v/search`, `/api/c/names`, `/api/c/name/<product>`, `/api/reddit/by-subreddit`, `/api/reddit/query/{questions,positive,cve}`, `/api/reddit/meta/subreddits` | releases, vendor records, community posts |
| `cisa.gov` | Known Exploited Vulnerabilities catalogue | verified vulnerability tier |
| `nvd.nist.gov` / CVE services | CVE records | verified vulnerability tier |
| `apple.com`, `circl.lu` | security RSS | vendor advisories |
| `news.google.com` | RSS | general news tier |
| `reddit.com` | public JSON | community tier |

`corpus_snapshot.CORPUS_HOST_HINTS` is the list that decides whether a replay miss
voids a run. Adding a source means adding it there too, or the freeze check silently
stops covering it.

## 5. Environment variables

| Variable | Values | Effect |
|---|---|---|
| `MARAG_RERANK` | `none` \| `bm25` \| `embed` \| `embed:<model>` | Ranking backend. Unknown values raise rather than defaulting, so a typo in a sweep fails loudly. Default `embed`. |
| `MARAG_CORPUS` | `` \| `record:<dir>` \| `replay:<dir>` | Frozen corpus. Empty means live, which makes two runs incomparable — never use empty for an ablation. |
| `OPENAI_API_KEY` | key | Enables `--judge openai:gpt-4o` and `raw:openai:*` arms. Absent by default; those arms are skipped, not faked. |

No `.env` is committed and no credential appears in the repo.

## 6. Repository map

| Path | Purpose |
|---|---|
| `specs/` | This spec set: mission, stack, pipeline, evaluation protocol, roadmap, reproducibility, writing |
| `multiagent_rag_v3.py` | The pipeline: rewriter, retriever with source fan-out, evaluator |
| `rerank.py` | Ranking backends (`none`/`bm25`/`embed`), spec-selected, honest about degradation |
| `corpus_snapshot.py` | Record/replay over `requests.get` and `urllib.request.urlopen`; the frozen-corpus control |
| `eval_harness/` | Tier-1 harness: runner, generators, judge, metrics, report, benchmarks |
| `eval_harness/FINDINGS.md` | The measurement narrative: defect found, misdiagnosed, correctly diagnosed, fixed |
| `build_multiecosystem_benchmark.py` | Mines live APIs into a 300-question stratified benchmark with provenance |
| `data/benchmark_300.json` + `.manifest.json` | The benchmark and its provenance manifest |
| `data/benchmark_100.json` | Stratified 100-question working subset; built deterministically from the 300 |
| `scripts/` | `phase0_env.sh`, `phase_ablation.sh`, `phase_judge.sh`, `check_runs.py` |
| `validation_gt.json` | 10-question ground-truth set used for the diagnostic work |
| `table_50_questions.json` | 50 Reddit-only questions; superseded by `benchmark_300` for claims |
| `tests/` | Regression tests, one per fixed defect |
| `results/<run_id>/` | Per-run artifacts. Gitignored — regenerable, and large |
| `data/corpus_snapshot*/` | Recorded corpora. Gitignored — ~1.3 MB per question |
| `app.py`, `DemoMain*.py`, `marag_app.py`, `unified_*.py` | Demo UIs. Not exercised by the harness. No claims. |

## 7. What is deliberately not pinned

State these in the paper's setup section rather than pretending to control them.

- **Live source content.** Frozen per experiment via `MARAG_CORPUS`, not globally.
- **Ollama model weights.** `:latest` tags move. Record `ollama list` output alongside
  a headline run.
- **Wall-clock latency.** Reported as measured on the machine above; not a claim.
