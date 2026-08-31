# Status — pick up here

Living handoff note. Anyone (or any session) starting work reads this first, then
`specs/roadmap.md` for the phase definitions. **Update this file at the end of a
work session**, not just the code.

Last updated: 2026-08-30, ~18:05.

---

## 1. Working rule: one writer at a time

This repository has been edited by more than one agent session simultaneously, and
it has cost real work twice:

- Benign: edits to `eval_harness/run_eval.py` from two sessions interleaved and both
  survived only by luck.
- Destructive: two sessions independently built the same stratified 100-question
  subset. One overwrote the other's `data/benchmark_100.json` *while a sweep was
  reading it*. The running experiment's `dataset_hash` (`c855b2accede`) no longer
  matched any file on disk (`67177cd53aab`), so the run was inadmissible under
  `evaluation-protocol.md` §5 and had to be discarded and restarted.

Before starting: run `git status`, and check `ps aux | grep run_eval` for a sweep
already in flight. **Never edit a dataset file while a run is reading it.** If you
must, write a new file rather than replacing one.

## 2. Where the work stands

| Phase | State | Evidence |
|---|---|---|
| 0 Environment | done | Python 3.11.15, 3 Ollama models, suite green |
| 1 Defects fixed | done | `a1c717c` fetch, `46ad7d0` qrels keys, `81f479d` findings |
| 2 Experiment infrastructure | done | `c2752b0` — frozen corpus, arm provenance, pool logging |
| 3 Frozen ablation, n=10 | **passed** | pool identical 20/20 in set and order, vs 0/10 before |
| 5 Ablation, n=100 | **running** | see §3 |
| 4 Independent judge | blocked | needs `OPENAI_API_KEY` |
| 6 Headline at n=300 | not started | after Phase 5 |
| 7 Artifact packaging | not started | — |
| 8 Paper | drafting | `specs/writing.md` |

Test suite: **247 passing**.

## 3. What is running right now

```
scripts/phase_ablation.sh data/benchmark_100.json data/corpus_snapshot_b300
```

Started 17:57:24. Four passes: one warm/record pass at `MARAG_RERANK=embed`, then
`none`, `bm25`, `embed` all replaying `data/corpus_snapshot_b300`. Log at
`/tmp/sweep100b.log`; it prints `##### DONE` when finished. Roughly 2 h total.

If it was interrupted, **do not restart from scratch** — `--resume <run_dir>`
continues it (added in `df11d2a`).

When it lands:

```bash
./venv311/bin/python scripts/check_runs.py     # admissibility, pool identity, arm table
```

## 4. Artifacts, and which ones do not travel

| Path | In git? | Note |
|---|---|---|
| `specs/`, `scripts/`, `tests/`, harness code | yes | — |
| `data/benchmark_100.json`, `benchmark_300.json` + manifests | yes | the datasets claims are made on |
| `results/qrels_cache.json` | yes, via a `.gitignore` exception | 1052 judgments; small, and it saves hours of re-judging in a fresh clone |
| `results/run_*/` | **no** | regenerable; archive them deliberately for the artifact submission |
| `data/corpus_snapshot_v1/` (13 MB), `corpus_snapshot_b300/` (23 MB) | **no** | large; **but a headline run is not reproducible without them** — see `specs/reproducibility.md` §2 |

The snapshots are the reproducibility asset. A fresh clone can rerun the code but
cannot reproduce a published number without the recorded corpus, because the live
sources have moved on. Archive the snapshot for the headline run with a DOI.

## 5. Live constraints and open threats

- **MDE.** n=100 detects **+0.154** absolute, not the +0.10 pre-registered in
  `evaluation-protocol.md` §6. A null at n=100 means "not detectable at this size".
  Only the 300-question run restores +0.10.
- **T2 judge independence — open.** `ollama:llama3.1` judges a pipeline whose
  rewriter is llama3.1. Needs `OPENAI_API_KEY` and Phase 4.
- **T3 pooling bias — declared.** Recall denominators are pool-relative. With
  `--judge-pool` the denominator widens and recall@5 drops from 0.933 to ~0.17
  on the n=10 set. The *ordering* of systems is unchanged; the absolute figures in
  `eval_harness/FINDINGS.md` are pool-narrow and must be restated before publication.
- **Latency is unmeasurable under replay** — responses come off disk. Cost numbers
  must come from a live run.
- **T8 closed by the data** — 0 `backfill_template` rows in either benchmark file.

## 6. Newest finding to carry forward

From Phase 3 (n=10, frozen corpus, `--judge-pool`): **the bottleneck has moved from
fetch to ranking.** Union fetch puts every judged-relevant document in the
multi-agent arm's pool (pool recall 1.000 against the baseline's 0.680), yet its
recall@5 does not exceed the baseline's. The ceiling is perfect and unconverted.
Ranking backend moves marag far more than the baseline (nDCG@3 +0.181 vs +0.029,
none→embed), consistent with that reading. Both CIs cross zero at n=10.
