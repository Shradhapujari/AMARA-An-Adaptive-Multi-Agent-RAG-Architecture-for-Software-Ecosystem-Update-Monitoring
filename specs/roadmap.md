# Roadmap — build sequence, gates, definitions of done

Spec-driven: `mission.md` (why) → `tech-stack.md` (with what) → `pipeline.md`
(how it is wired) → `evaluation-protocol.md` (how it is measured) → **this file**
(in what order, and how you know a phase is finished).

Rules: do not start a phase with the previous one's DoD unchecked; do not start a
phase with a red test suite; a phase whose gate fails goes back, it does not get
waived.

Run every check with the project interpreter: `./venv311/bin/python`.

---

## Phase 0 · Environment is real — DONE

**Goal.** A third party can stand the artifact up and get a green suite.

```bash
./venv311/bin/python -V                      # expect 3.11.15
./venv311/bin/pip install -r requirements.txt
curl -s http://localhost:11434/api/tags      # llama3.1, mistral, nomic-embed-text
./venv311/bin/python -m pytest tests eval_harness -q
```

**DoD**
- [x] Python 3.11.15 in `venv311`, dependencies pinned in `requirements.txt`.
- [x] Three Ollama models present.
- [x] Suite green — 219 passed, 1 skipped.
- [x] No credential in the repo.

---

## Phase 1 · Defects found and fixed — DONE

**Goal.** The pipeline's two measured defects are fixed, each with a regression test.

**DoD**
- [x] D1 fetch-time: rewrite augments rather than replaces (`RetrieverAgent.run`).
- [x] D2 ranking-time: ranking scores against the original question (`rerank.py`).
- [x] D3 qrels keys hash the question, not the row id (`46ad7d0`).
- [x] D4 `qrels.json` records what scored *this* run, not the accumulating cache.
- [x] Each has a test that fails on the old behaviour.
- [x] `eval_harness/FINDINGS.md` narrates find → misdiagnose → diagnose → fix.

**Gate** — `./venv311/bin/python -m pytest tests -q` green.

---

## Phase 2 · Experiment infrastructure — DONE

**Goal.** A run can prove what it was. Without this, no table is admissible.

**DoD**
- [x] `corpus_snapshot.py`: record/replay over `requests.get` and `urllib.request.urlopen`.
- [x] Replay miss goes live, is recorded, and is counted by host.
- [x] Corpus-host misses set `frozen: false` and print a WARNING; model-host misses do not.
- [x] `config.json` carries `rerank_requested`, `rerank_spec`, `rerank_degraded`, `corpus{}`.
- [x] `per_query.jsonl` carries `pool_size`, `pool_doc_ids`, `pool_recall`, `rerank_spec`, `rerank_degraded`.
- [x] `--judge-pool` widens judging to the candidate pool; `pool_recall` is `None` without it.
- [x] 28 new tests (`test_corpus_snapshot.py`, `test_pool_diagnostics.py`).

**Gate** — a two-question record run shows `rerank_spec = embed:nomic-embed-text`,
non-zero `recorded`, and `pool_size > n_docs`. *Verified.*

---

## Phase 3 · Frozen-corpus ranking ablation on `validation_gt` — DONE

**Goal.** Re-run the three ranking arms with the corpus actually frozen and the arm
actually recorded, replacing the void 2026-08-30 sweep.

```bash
SNAP=data/corpus_snapshot_v1
COMMON="--dataset validation_gt.json --generators marag,single_agent \
        --judge ollama:llama3.1 --judge-pool"
MARAG_RERANK=embed ./venv311/bin/python -m eval_harness.run_eval $COMMON --corpus record:$SNAP
for arm in none bm25 embed; do
  MARAG_RERANK=$arm ./venv311/bin/python -m eval_harness.run_eval $COMMON --corpus replay:$SNAP
done
```

**DoD**
- [x] Four run directories; three replay arms share one snapshot.
- [x] Every replay arm reports `corpus.frozen == true`, `corpus_misses == 0`.
- [x] `rerank_spec` in each `config.json` matches its intended arm.
- [x] Pool recall reported per arm — marag 1.000, single_agent 0.680.
- [x] Identical questions produce identical `pool_doc_ids` across arms: **20/20
      identical in set and in order**, against 0/10 stable before the freeze.

Runs: `run_1788134763` (none), `run_1788134906` (bm25), `run_1788135008` (embed),
all replaying `data/corpus_snapshot_v1` recorded by `run_1788133873`.

**Two consequences to carry forward.**

1. **The bottleneck has moved from fetch to ranking.** Union fetch puts every
   judged-relevant document in marag's pool (pool recall 1.000 against the
   baseline's 0.680), yet marag's recall@5 does not exceed the baseline's. The
   ceiling is perfect and unconverted; C1/C2 are about fetch, and what remains is a
   ranking problem. Ranking backend moves marag (nDCG@3 +0.181 none→embed) far more
   than it moves the baseline (+0.029), which is consistent with that reading.
2. **Absolute recall figures in `FINDINGS.md` are pool-narrow.** With `--judge-pool`
   the denominator widens from "relevant among returned" to "relevant among
   considered", and recall@5 falls from 0.933 to ~0.17. The ordering of systems is
   unchanged; the absolute numbers are not comparable. Re-state them before
   publication.

Latency is not measurable under replay — responses are served from disk, so the
0.05–0.5 s figures in these runs are an artifact of the control, not a result.

**Gate** — the pool-identity check. It is the single strongest evidence that the
control works, and it costs one comparison over the artifacts.

---

## Phase 4 · Independent judge

**Goal.** Close T2. The judge must not share a model family with a system under test.

```bash
export OPENAI_API_KEY=...
MARAG_RERANK=embed ./venv311/bin/python -m eval_harness.run_eval \
  --dataset validation_gt.json --generators marag,single_agent \
  --judge openai:gpt-4o --corpus replay:data/corpus_snapshot_v1
```

**DoD**
- [ ] Headline run re-judged with an independent judge.
- [ ] Both judges' rankings of the systems reported side by side.
- [ ] Agreement quantified (Cohen's κ on the graded labels).
- [ ] If the judges disagree on the ranking, that disagreement becomes a finding and
      the paper reports both; it does not pick the flattering one.

**Gate** — κ reported, whatever its value.

---

## Phase 5 · Scale to `benchmark_300`

**Goal.** Move every claim off n=10 onto the set the power analysis supports.

Budget honestly first: 300 questions × 2 systems × ~20 s ≈ 3.5 h per arm, plus pool
judging on the record pass. Run the record pass overnight; replay arms are cheaper on
the network but still pay for models.

**DoD**
- [ ] Provenance mix reported: `mined_reddit_title` / `mined_release_record` /
      `backfill_template` shares.
- [ ] Headline metrics reported with and without backfilled rows (T8).
- [ ] All admissibility boxes in `evaluation-protocol.md` §5 ticked.
- [ ] Every point estimate carries a 95 % CI.
- [ ] Effect sizes reported next to p-values; Bonferroni α = 0.0167 for the three-arm family.
- [ ] Any arm difference below the pre-registered +0.10 MDE reported as "not
      detectable at this sample size", not as a null and not as a trend.
- [ ] ≥3 seeds where the metric is stochastic.

**Gate** — `evaluation-protocol.md` §5 checklist, all boxes, read off `config.json`.

---

## Phase 6 · The C1/C2 headline experiment

**Goal.** The result the paper is actually about: replace-mode versus augment-mode
fetch, on one frozen corpus, at n=300.

**DoD**
- [ ] Both fetch modes run against the identical snapshot.
- [ ] Pool-membership count reproduced at scale — the n=10 statement was "22 of 23
      relevant documents the baseline retrieved were never in marag's pool".
- [ ] Pool recall reported for both modes; this is the mechanism, not just the effect.
- [ ] Cost of union fetch reported next to the gain (roughly 2× fan-out).
- [ ] C3 reported as a negative result with CIs, in the same table, not in a footnote.

**Gate** — the mechanism (pool recall) and the effect (nDCG/recall) move together. If
the effect appears without the mechanism, the explanation is wrong and Phase 6 fails.

---

## Phase 7 · Artifact packaging

**Goal.** ACM artifact badges. Details in `specs/reproducibility.md`.

**DoD**
- [ ] `README.md` reproduces the headline table from a clean clone in documented steps.
- [ ] Snapshot for the headline run archived with a DOI (Zenodo or ACM DL).
- [ ] `ollama list` output and `pip freeze` captured alongside the headline run.
- [ ] A clean-clone dress rehearsal on a second machine, written up as
      `docs/reproduction-check.md`.
- [ ] Demo UIs clearly marked as unverified and claim-free.

**Gate** — someone who has not touched this repo runs the documented steps and gets
the headline table.

---

## Phase 8 · Paper

**Goal.** Submission. Structure, integrity practice, and AI disclosure in
`specs/writing.md`.

**DoD**
- [ ] Every number in every table traces to a `run_id` recorded in the caption.
- [ ] Every threat in `evaluation-protocol.md` §8 either closed or declared in the text.
- [ ] The original +17.2 % claim explicitly retracted and explained (C4).
- [ ] Negative result (C3) stated in the abstract, not only in the discussion.
- [ ] Generative-AI use disclosed per ACM policy.
- [ ] Similarity check run before submission.

---

## Status board

| Phase | State | Blocker |
|---|---|---|
| 0 Environment | done | — |
| 1 Defects fixed | done | — |
| 2 Experiment infrastructure | done | — |
| 3 Frozen ablation, n=10 | done | gate passed 20/20 |
| 4 Independent judge | not started | needs `OPENAI_API_KEY` |
| 5 Scale to 300 | not started | Phase 3 gate; ~4 h/arm compute |
| 6 C1/C2 headline | not started | Phase 5 |
| 7 Artifact packaging | not started | Phase 6 |
| 8 Paper | drafting | Phases 4–6 |

## Standing hazard

More than one agent session has edited this repository concurrently, and edits have
crossed inside `eval_harness/run_eval.py`. Before any phase that writes code: check
`git status`, and prefer one writer at a time. A lost edit here is a lost experiment.
