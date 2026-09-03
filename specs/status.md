# Status — pick up here

Living handoff note. Anyone (or any session) starting work reads this first, then
`specs/roadmap.md` for the phase definitions, then `HANDOFF.md` if the paper is
what you're picking up. **Update this file at the end of a work session**, not
just the code.

Last updated: **2026-09-03** (Week 2 update — see §10, appended at the end; the
sections above it are the 2026-08-31 snapshot from the infra/eval-side session
and are kept verbatim so the record of what was believed when stays readable).
The paper-side session should re-check `HANDOFF.md`'s own "Last updated" line
separately — the two docs are drifting apart and someone should merge or
clearly split them.

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

## 8. Paper audit, 2026-08-31 ~02:15 (infra/eval session)

Checked `paper/tosem_amara.tex` numeric claims against `scripts/check_runs.py`
output. No fabricated or stale numbers found — Table `scaled-ablation` (n=100,
frozen corpus) matches an admissible run within rounding, and the paper is
already honest that `scaled-retrieval` is *not* frozen (says so in its own
caption).

**One gap:** neither scaled-ablation nor scaled-retrieval names its source
`run_*` directory. `evaluation-protocol.md` §5 requires this, and it is what
the artifact appendix (`reproducibility.md`) will need to point reviewers at
the right `results/` folder. Suggest adding `run_id` to each caption before
submission — cheap, and closes a real gap between the paper and its evidence.

## 9. Top_k sweep result (05:43) — the throttle question, answered, and it's not a clean answer

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


---

## 10. Week 2 update — 2026-09-03 (COMP 291 Week 2, Aug 31 – Sep 4)

Written for the Thursday implementation review. Everything below is checked
against a run id or a command output, per §6.

### 10.1 Phase 6 is done: the headline at n=300

`specs/status.md` §2 listed Phase 6 ("Headline at n=300") as **not started**.
It has since completed. **`run_1788302755_7cdc5685d75a`** — the whole
`data/benchmark_300.json`, no `--limit`, three arms (`marag`,
`marag:ollama:llama3.1`, `single_agent:ollama:llama3.1`), synthesis model held
constant, `embed:nomic-embed-text` reranker, `ollama:llama3.1` judge.

Paired Wilcoxon vs `single_agent`, Holm-corrected:

| Metric | marag delta | p_holm | W/T/L |
|---|---:|---:|---:|
| nDCG@3 | +0.009 | 0.302 | 16/269/15 |
| nDCG@5 | +0.001 | 1.000 | 20/250/30 |
| Recall@5 | -0.011 | 0.502 | 12/267/21 |
| MRR | +0.006 | 0.667 | 4/290/6 |
| Faithfulness (template) | **-0.196** | **<0.001** | 33/50/217 |
| Faithfulness (prose, same retrieval) | +0.002 | 0.787 | 20/262/18 |

What it settles, and what it does not:

1. **The parity result is now well-powered.** The "underpowered at n=100"
   objection in §5 (MDE) is no longer available for the retrieval family.
2. **Parity is not the benchmark failing to discriminate.** Only 100 of 300
   questions (33.3%) produce identical top-k lists; 65.0% retrieve materially
   different documents; marag's mean candidate pool is **23.1** vs **15.5**.
   The extra retrieval is real and it is inert — a stronger claim than parity.
3. **The format confound is confirmed, not suspected.** Same retrieval, prose
   instead of template, and the 0.196 deficit vanishes.
4. **It is not a frozen comparison.** The run spans two calendar days (paused
   at 93/300, resumed), so it is incomparable to any *other* run. The pairing
   is intact — the three arms execute back-to-back per question, median 129 s —
   but for byte-identical documents across arms cite the frozen ladder replay
   `run_1788422938_67177cd53aab` instead.
5. **Quote the medians, never the means.** Questions 164 and 165 recorded
   1,000–5,200 s on *every* arm (host stall). Medians: 20.3 s marag, 26.3 s
   marag_llm, 8.8 s single_agent — **2.3x** and **3.0x**.

Full write-up: `eval_harness/FINDINGS.md` Finding 6; provenance and the caution
list: `results/PROVENANCE.md`.

### 10.2 Harness fix shipped with it

`eval_harness/run_eval.py` printed hit/miss counts for `record` mode, where
neither is counted — so a recording pass that stored 13,283 responses reported
"0 hits, 0 misses" and read as if it had captured nothing. It now reports the
number of responses actually stored and the directory they went to. Commit
`2f1107c`.

### 10.3 Phase table, current

| Phase | State | Change since 08-31 |
|---|---|---|
| 0 Environment | done | test suite now **629 passing** offline (was 349) |
| 1 Defects fixed | done | — |
| 2 Experiment infrastructure | done | — |
| 3 Frozen ablation, n=10 | passed | — |
| 5 Ablation, n=100, clean corpus | admissible per-arm | superseded for the headline by the frozen ladder replay |
| 4 Independent judge | **still blocked** | needs `OPENAI_API_KEY`; unchanged |
| 6 Headline at n=300 | **done** | §10.1 |
| 7 Artifact packaging | not started | the corpus snapshots still need a DOI archive |
| 8 Paper | submitted | TOSEM, 2026-09-01 |

### 10.4 Deployment, re-verified 2026-09-03

<https://software-update-questions.streamlit.app/> — loaded, ran
"Any critical Linux updates today?" end to end through all agents. Temporal
Grounder reported *Grounded*, Vendor & Intent resolved *linux · security*,
Query Rewriter fell back to *Rule-based (fallback)* as expected with no model
on Streamlit Cloud, and the retrieval agents returned live documents. The
labelling of the rule-based path is working as `docs/Deployment.md` describes.

### 10.5 Also landed today

- **The paper reports every rung of the ladder** (`4d13730`, merged as PR #13).
  Section 3.6 had said A2, A4 and the fourth rendering cell were implemented
  but not run, on two conditions; the first — a recorded snapshot in replay, so
  rungs differ by capability rather than drift — is now met. New Section 4.5
  reports the frozen run, Table 2 gains A0 and A1g, and Tables 6 and 8 are
  qualified as a lower bound because they predate the release-fetch repair.
  **This commit sat unpushed for the whole day**: it was made on
  `eval/benchmark-300-complete` roughly a minute after that branch had already
  been pushed and PR'd, so the merge to main did not include it. Check
  `git log --oneline main..<branch>` on every local branch before assuming a
  merged branch is empty.
- **The review deck now covers the whole project**, not one week — sixteen
  slides, every number traceable to a run id. The deck and its speaker script
  are kept outside the repository deliberately: they are presentation
  artifacts, not things the system needs to run, and a binary `.pptx` in git
  is a merge conflict waiting to happen. The repository holds the evidence
  they are built from — `eval_harness/FINDINGS.md` and `results/PROVENANCE.md`.
- **Documentation currency.** `docs/Benchmarks-and-Data.md` still described the
  300-question run as incomplete at 68 of 300; corrected. Test counts in the
  README, `docs/Overview.md` and `docs/Running-the-System.md` read 477 and now
  read 629, verified from a clean clone (628 passed, 1 skipped after
  `pip install -r requirements.txt` into a fresh venv).

### 10.6 What is still open, in priority order

1. **Phase 4, independent judge.** Blocked on `OPENAI_API_KEY` since 08-31.
   `ollama:llama3.1` still judges a pipeline whose rewriter and one arm are
   llama3.1. This is the largest live threat to every number in this file.
2. **Frozen n=300.** §10.1 item 4. A replay run against a single-writer
   snapshot directory would make the large-sample result citable alongside the
   ladder rather than only as corroboration.
3. **Artifact packaging (Phase 7).** The snapshots are the reproducibility
   asset and none of them are archived. `corpus_snapshot_b300_full_0901` is 84
   MB / 7,899 files.
4. **`HANDOFF.md` vs this file.** Still drifting. Merge or split them.
