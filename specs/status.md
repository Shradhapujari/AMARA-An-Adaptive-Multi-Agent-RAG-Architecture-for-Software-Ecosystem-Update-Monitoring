# Status — pick up here

Living handoff note. Anyone (or any session) starting work reads this first, then
`specs/roadmap.md` for the phase definitions, then `HANDOFF.md` if the paper is
what you're picking up. **Update this file at the end of a work session**, not
just the code.

Last updated: 2026-08-31, ~02:00 (this update written by the infra/eval-side
session; the paper-side session should re-check `HANDOFF.md`'s own "Last
updated" line separately — the two docs are drifting apart and someone should
merge or clearly split them).

---

## 1. Working rule: one writer at a time — read this before touching anything

This repo has now cost real work **three** times to concurrent sessions:

1. Two sessions built the same stratified 100-question subset; one overwrote
   the other's `data/benchmark_100.json` mid-sweep. Discarded and restarted.
2. **2026-08-30 ~19:52 — a script was edited while it was executing.**
   `670da9c` landed on `scripts/phase_ablation.sh` mid-run. Bash streams a
   script from a byte offset rather than loading it whole, so the commit
   shifted every offset under the running shell; execution resumed inside a
   comment and tried to run the word `leak` out of "leaves gaps that leak on
   every arm". `set -euo pipefail` killed it after the record pass — ~4 hours
   of GPU time produced one inadmissible run. **Fixed in `ebdeeef`**: both
   `phase_ablation.sh` and `phase_topk.sh` now wrap their body in
   `main() { ... }; main "$@"; exit $?`, which forces bash to parse the whole
   script before the first line runs. Verified by appending garbage to a
   running copy — it now completes unaffected. Editing a running shell script
   is still a bad idea; the wrapper is a safety net, not permission.
3. **2026-08-31 ~01:00–01:24 — three `run_eval` processes shared one GPU.**
   Throughput dropped from ~160 rows/hour (solo) to ~20 rows/hour (three-way).
   Two of the three were killed by explicit user instruction at 01:24 (pids
   98304/98308 — a redundant `marag,single_agent --judge-pool` arm loop).
   **Nothing was lost**: the killed run's `per_query.jsonl` (162 rows, 81
   questions × 2 systems) parses cleanly and resumes with
   `--resume run_1788161029_67177cd53aab`. Throughput recovered to
   ~227 rows/hour solo. Also exposed: `_save_qrels_cache` wrote
   `qrels_cache.json` in place, so two writers sharing a results dir could
   tear it — silently, because `_load_qrels_cache` catches the parse error and
   returns `{}`, discarding every judgment. **Fixed in `9a8945a`** (atomic
   temp-file + `os.replace`). It did not bite this time, but it was live for
   both processes involved.

Before starting: run `git status`, `git log --oneline -15`, and
`ps aux | grep run_eval` for anything already in flight. **Never edit a file a
running process has open** — a dataset, a script it's executing, a shared
cache — write a new one or wait. If you must stop someone else's run, kill the
wrapper/parent first (so it can't spawn its next child), verify the partial
run's `per_query.jsonl` still parses, and tell them the `--resume` id.

## 2. Where the work stands

| Phase | State | Evidence |
|---|---|---|
| 0 Environment | done | Python 3.11.15, 3 Ollama models, suite green (349 tests) |
| 1 Defects fixed | done | `a1c717c` fetch, `46ad7d0` qrels keys, `81f479d` findings |
| 2 Experiment infrastructure | done | frozen corpus, arm provenance, pool logging, atomic cache, edit-proof scripts |
| 3 Frozen ablation, n=10 | passed | see `eval_harness/FINDINGS.md` for caveats |
| 5 Ablation, n=100, clean corpus | **admissible per-arm; pool-identity gate at 180/200** | see §3 — a real but explained gap |
| 4 Independent judge | blocked | needs `OPENAI_API_KEY` |
| 6 Headline at n=300 | not started | after Phase 5 lands admissible |
| 7 Artifact packaging | not started | — |
| 8 Paper | active, deadline 2026-09-01 | `HANDOFF.md` is the doc of record for this track |

Test suite: **349 passing**, offline. Run `git log --oneline 81f479d..HEAD` for
the full list of ~35 commits since the last status snapshot (paper edits,
`--resume` fixes, corpus strict-replay, this note's fixes) — too many to
summarize individually here without re-verifying each one; do that before
relying on a specific commit's claim.

## 3. What is running right now, and what's still broken

**Running:** pid varies by the time you read this — check
`ps aux | grep eval_harness.run_eval`. As of 02:00, one process (started
~00:22) is running a 3-arm comparison on `benchmark_100.json`
(`marag`, `marag:ollama:llama3.1`, `single_agent:ollama:llama3.1`,
`--judge-pool`), at ~132/300 rows, ETA roughly 02:35.

**Queued, not yet started:** a top_k sweep (`top_k` 4/10/20, `MARAG_RERANK=embed`
pinned, same frozen corpus) is parked waiting for a sustained idle window —
see `/tmp/topk_sweep.log`, marker `##### QUEUED`. It auto-starts once no
`run_eval`/`phase_ablation.sh` has been running for 60s, then takes ~4h. Read
its result with `./venv311/bin/python scripts/topk_report.py` once
`/tmp/topk_sweep.log` shows `##### TOPK DONE`.

Motivating question for that sweep: on the n=100 embed arm, `marag` holds far
more judged-relevant documents in its pool than the baseline (pool recall 0.979
vs 0.845) but does not convert that into better final retrieval (recall@5 0.391
vs 0.401, nDCG@3 0.659 vs 0.649) — see `run_1788160991_67177cd53aab`. The naive
"the reranker is worse" reading fails a matched-ceiling control (queries where
both arms hold the same number of relevant docs: diff -0.049, p=0.16, 95% CI
crosses zero). `top_k=4` is the suspected throttle. If the gap opens at k=10/20,
the architecture works and the config was hiding it; if it stays flat, the
deficit is in ranking after all.

**STILL BROKEN as of the last check (02:00):** `scripts/check_runs.py` reports
**every completed embed-arm run on `benchmark_100.json` as NOT ADMISSIBLE**,
even the ones after the strict-replay corpus fix (`9405592`,
`1db8bb9`):

```
run_1788160991_67177cd53aab   corpus_misses=6    (mode=replay, post strict-replay fix)
run_1788146393_67177cd53aab   corpus_misses=589  (mode=replay, an EARLIER replay pass)
```

**Correction to an earlier version of this note**: `run_1788146393` was not "the
record pass" from any sweep — its own `config.json` says `mode: "replay"`,
`recorded: 3760`. A replay-mode run backfills every miss it hits back into the
snapshot directory, so this run wrote 3760 responses into
`data/corpus_snapshot_b100_clean` while claiming to replay it. That is the
warm-replay leak `phase_ablation.sh`'s own header comment warns about
("Warm-replaying a snapshot inherited from an earlier, differently-scoped run
leaves gaps that leak on every arm"). Caught by a peer session, verified here
against the raw `config.json` before writing this correction in.

Consequence: **`data/corpus_snapshot_b100_clean` is no longer a frozen
artifact.** It has been written across at least two sessions over several
hours (mtimes spanning 2026-08-30 20:19 through 2026-08-31 01:31, 4283
entries), so record/replay purity cannot be asserted over it, regardless of
what any single run's `corpus_misses` count reads. **Phase 5 is being re-run
into a fresh directory, `data/corpus_snapshot_b100_p5`**, precisely to avoid
this. Check `results/` for a run against that directory before trusting any
n=100 number; anything still citing `corpus_snapshot_b100_clean` is suspect no
matter its miss count.

**UPDATE 04:16 — Phase 5 completed on the fresh directory, and the picture
changed again.** All three arms (`run_1788172664` none, `run_1788173743`
bm25, `run_1788174490` embed:nomic-embed-text) report `corpus_misses=0` — the
fresh single-writer directory genuinely fixed the contamination problem. But
`check_runs.py`'s stronger pool-IDENTITY gate (do all three arms see the same
pre-rerank candidates for a given question, not just "did any of them go
live") still fails: **180/200, not 200/200.**

Root cause found and fixed, `526afa9`: `extract_vendor` broke tied vendor
matches by iterating a raw Python `set`, whose order is randomized per
process by `PYTHONHASHSEED`. `phase_ablation.sh` launches each arm as a
separate process, so the identical question could resolve to a different
vendor on different arms, changing which endpoints got queried — a frozen
corpus does not help if the retrieval layer asks it different questions.
Verified directly: `extract_vendor("...rust-lang rust v1.92.0...")` returned
`"rust"` under most `PYTHONHASHSEED` values and `"release"` (a spurious
registry collision) under others. Fixed with `sorted(set(...))`; 4 new tests
in `tests/test_vendor_extraction_determinism.py`, 403 total passing.

**This fix landed mid-sweep**, after `none` and `bm25` had already run — so
none of the three Phase 5 arms benefited from it, which is exactly why
180/200 is not 200/200 here. The fix is real and forward-looking: anything
launched after `526afa9` should see full pool identity. Whether to re-run
`none`/`bm25`/`embed` cleanly on top of the fix, or accept this run with the
caveat stated, is an open call — not made unilaterally here.

Despite the imperfect pool-identity gate, the **admissibility numbers
themselves reproduce the paper's headline finding independently**: rerankers
improve monotonically (none → bm25 → embed, nDCG@3 for `marag`: 0.486 → 0.627
→ 0.656), yet `marag` still does not beat `single_agent` at the best
reranker (nDCG@3 0.656 vs 0.646, recall@5 0.387 vs 0.388) — consistent with
`tab:scaled-retrieval` in the paper. Full arm table: `scripts/check_runs.py`.

## 4. Artifacts, and which ones do not travel

| Path | In git? | Note |
|---|---|---|
| `specs/`, `scripts/`, `tests/`, harness code, `HANDOFF.md` | yes | — |
| `data/benchmark_100.json`, `benchmark_300.json` + manifests | yes | the datasets claims are made on |
| `results/qrels_cache.json` | yes, via a `.gitignore` exception | 3166+ judgments as of 01:35; now written atomically (`9a8945a`) |
| `results/run_*/` | **no** | regenerable; archive deliberately for artifact submission |
| `data/corpus_snapshot_v1/` (12M), `corpus_snapshot_b300/` (57M), `corpus_snapshot_b100_clean/` (42M) | **no** | large; **a headline run is not reproducible without them** |

The snapshots are the reproducibility asset. Archive the one behind the
headline run with a DOI before submission.

## 5. Live constraints and open threats

- **Admissibility (new, see §3).** The clean-corpus n=100 ablation is not yet
  admissible on any completed run. Do not quote its numbers as a frozen-corpus
  result until `check_runs.py` shows `corpus_misses=0`.
- **MDE.** n=100 detects roughly +0.15 absolute on recall/nDCG-scale metrics,
  not the +0.10 pre-registered. A null at n=100 means "not detectable at this
  size", not "no effect" — this is exactly why the top_k sweep and eventually
  n=300 matter.
- **T2 judge independence — open.** `ollama:llama3.1` judges a pipeline whose
  rewriter and one arm are also llama3.1. Needs `OPENAI_API_KEY` and Phase 4.
- **T3 pooling bias — declared, not fixed.** Recall/nDCG denominators are
  pool-relative (only documents the run's own arms fetched are judged unless
  `--judge-pool` is set). This inflates absolute recall/nDCG but the *paired*
  within-run comparison stays valid, since both arms share one pool.
- **Latency is unmeasurable under replay** — responses come off disk, and
  tonight's GPU contention (§1.3) makes any latency number from ~00:30–01:24
  additionally unusable regardless.
- **Concurrent sessions.** Still true, still the biggest risk. See §1.

## 6. Two things every fresh session should verify before citing a number

1. `./venv311/bin/python scripts/check_runs.py` — is the run you're about to
   cite actually admissible (`corpus_misses=0`)? Runs above are not.
2. `./venv311/bin/python -m pytest tests/ -q` — should read 349 passing (or
   more) offline. If it doesn't, something regressed since this note.

## 7. Which doc to read next

- Picking up the **paper**: `HANDOFF.md` (deadline 2026-09-01, TOSEM). It has
  its own numbers table and open-items list; cross-check every number against
  a currently-admissible run before trusting it, per §6.
- Picking up the **experiment**: this file, then `evaluation-protocol.md` for
  what "admissible" and "MDE" mean precisely, then §3 above for exactly where
  things stand right now.

## 8. Top_k sweep result (05:43) — the throttle question, answered, and it's not a clean answer

`scripts/topk_report.py` against the three completed runs (`top_k` 4/10/20,
same frozen `corpus_snapshot_b100_p5`, `MARAG_RERANK=embed` fixed). Pool
recall (ceiling) is stable across all three, as it should be for a fixed
corpus: `marag` 0.982, `single_agent` 0.846.

**It reverses, not just closes.** At `top_k=10`, `marag` is BEHIND on
recall@10 by −0.088 (CI [−0.139, −0.039], p=0.0007 — clears zero). At
`top_k=20`, `marag` is AHEAD on recall@20 by +0.075 (CI [+0.036, +0.118],
p=0.0006 — also clears zero). Both are real signals, not noise, and they
point opposite directions.

Mechanism, from the conversion numbers: `single_agent` converts its smaller
pool efficiently at small `k` (0.806 shipped/held at k=10 vs `marag`'s
0.619) — it's better at packing its top hits into few slots. `marag`'s much
larger raw pool (0.982 vs 0.846 pool recall) only starts to dominate once
given enough room; by k=20 conversion is nearly even (0.927 vs 0.987) and
the raw-pool advantage wins out.

Matched-ceiling (equal fetch, isolates ranking) confirms this isn't a fetch
artifact: at k=10, `marag` is significantly worse even with equal pool
(diff −0.400, p=0.0005); by k=20 the matched-ceiling gap is smaller and not
significant (diff −0.089, p=0.10).

**Reading:** `top_k=4` (the paper's config) wasn't hiding a clean advantage —
it was hiding a genuine ranking deficit at small windows that a large-enough
window eventually outruns via raw fetch volume. Neither "the reranker is
worse" nor "the architecture works, config was throttling it" is the whole
story; both are true at different `k`. This is a nuance, not a simple
vindication either way — worth stating precisely rather than picking the
convenient half.

Runs: `run_1788175676` (k=4), `run_1788176239` (k=10), `run_1788178165`
(k=20), all on `corpus_snapshot_b100_p5`, n=93 scorable (pool recorded).
