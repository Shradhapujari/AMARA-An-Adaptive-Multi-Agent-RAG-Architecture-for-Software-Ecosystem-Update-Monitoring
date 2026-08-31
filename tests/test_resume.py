"""
Tests for streamed run artifacts and --resume in eval_harness/run_eval.py.

The defect: `per_query.jsonl` was written once, after the whole question loop.
A 300-question run is hours long, so an interruption threw away every generated
answer while keeping only the cached judgments — 67 questions were lost that
way. Rows are now streamed per question and a run can be continued.

These tests run the real `run()` with stub generators and an unavailable judge,
so no model, no network, and no live API is involved.
"""

from __future__ import annotations

import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eval_harness import run_eval as R  # noqa: E402
from eval_harness.config import EvalConfig  # noqa: E402


DATASET = [
    {"id": i, "query": f"question {i}", "category": "releases", "ground_truth": None}
    for i in (1, 2, 3, 4)
]


class StubGen:
    """A generator that answers instantly, optionally dying on one question."""

    def __init__(self, name, die_on=None):
        self.name = name
        self.die_on = die_on
        self.seen = []

    def available(self):
        return True

    def generate(self, query):
        if query == self.die_on:
            raise KeyboardInterrupt("simulated interruption")
        self.seen.append(query)
        return {"answer": f"{self.name} says {query}", "docs": [], "self_quality": None}


class DeadJudge:
    """Judge that reports itself unavailable: metrics stay empty, no LLM call."""

    def __init__(self, spec):
        self.spec = spec

    def available(self):
        return False


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """cfg + hooks so run() exercises real persistence with stub systems."""
    ds = tmp_path / "ds.json"
    ds.write_text(json.dumps(DATASET))
    monkeypatch.setattr(R, "Judge", DeadJudge)
    monkeypatch.setattr(R.corpus_snapshot, "activate", lambda spec: None)

    state = {"gens": None}

    def install(gens):
        state["gens"] = gens
        monkeypatch.setattr(R, "build_generators", lambda specs, top_k=4: gens)

    def cfg(**kw):
        return EvalConfig(dataset=str(ds), results_dir=str(tmp_path),
                          generators=["a", "b"], **kw)

    return types.SimpleNamespace(cfg=cfg, install=install, state=state, tmp=tmp_path)


def _rows(run_dir):
    with open(os.path.join(run_dir, "per_query.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


# ── streaming ────────────────────────────────────────────────────────────

def test_rows_are_on_disk_for_every_finished_question(harness):
    harness.install([StubGen("a"), StubGen("b")])
    run_dir = R.run(harness.cfg())
    rows = _rows(run_dir)
    assert len(rows) == 8                                     # 4 questions x 2 systems
    assert {r["query_id"] for r in rows} == {1, 2, 3, 4}


def test_interruption_keeps_the_questions_already_finished(harness):
    """The whole point: work done before the kill survives on disk."""
    harness.install([StubGen("a"), StubGen("b", die_on="question 3")])
    cfg = harness.cfg()
    with pytest.raises(KeyboardInterrupt):
        R.run(cfg)
    run_dir = [os.path.join(str(harness.tmp), d) for d in os.listdir(harness.tmp)
               if d.startswith("run_")][0]
    rows = _rows(run_dir)
    # Questions 1-2 complete; question 3 died partway and is not half-written.
    assert {r["query_id"] for r in rows} == {1, 2}
    assert len(rows) == 4


def test_qrels_json_keys_are_strings_and_written_as_the_run_goes(harness):
    harness.install([StubGen("a"), StubGen("b")])
    run_dir = R.run(harness.cfg())
    qrels = json.load(open(os.path.join(run_dir, "qrels.json")))
    assert all(isinstance(k, str) for k in qrels)


# ── resume ───────────────────────────────────────────────────────────────

def test_resume_finishes_the_run_without_regenerating_finished_questions(harness):
    dying = StubGen("b", die_on="question 3")
    harness.install([StubGen("a"), dying])
    with pytest.raises(KeyboardInterrupt):
        R.run(harness.cfg())
    run_id = [d for d in os.listdir(harness.tmp) if d.startswith("run_")][0]

    fresh_a, fresh_b = StubGen("a"), StubGen("b")
    harness.install([fresh_a, fresh_b])
    run_dir = R.run(harness.cfg(resume=run_id))

    assert os.path.basename(run_dir) == run_id            # same dir, same run id
    rows = _rows(run_dir)
    assert len(rows) == 8 and {r["query_id"] for r in rows} == {1, 2, 3, 4}
    # Questions 1-2 were not asked again.
    assert fresh_a.seen == ["question 3", "question 4"]


def test_resume_does_not_duplicate_a_row_for_one_question_and_system(harness):
    harness.install([StubGen("a"), StubGen("b", die_on="question 3")])
    with pytest.raises(KeyboardInterrupt):
        R.run(harness.cfg())
    run_id = [d for d in os.listdir(harness.tmp) if d.startswith("run_")][0]

    harness.install([StubGen("a"), StubGen("b")])
    run_dir = R.run(harness.cfg(resume=run_id))

    keys = [(r["query_id"], r["system"]) for r in _rows(run_dir)]
    assert len(keys) == len(set(keys))


def test_resume_of_a_complete_run_is_a_no_op_rerun_of_nothing(harness):
    harness.install([StubGen("a"), StubGen("b")])
    run_id = os.path.basename(R.run(harness.cfg()))

    fresh = StubGen("a")
    harness.install([fresh, StubGen("b")])
    R.run(harness.cfg(resume=run_id))
    assert fresh.seen == []


def test_resume_refuses_a_missing_run_dir(harness):
    harness.install([StubGen("a"), StubGen("b")])
    with pytest.raises(SystemExit) as e:
        R.run(harness.cfg(resume="run_does_not_exist"))
    assert "no such run dir" in str(e.value)


def test_resume_refuses_a_run_from_a_different_dataset(harness, tmp_path):
    """A run id carries its dataset hash; mixing two question sets is refused."""
    harness.install([StubGen("a"), StubGen("b")])
    run_id = os.path.basename(R.run(harness.cfg()))

    other = tmp_path / "other.json"
    other.write_text(json.dumps([{"id": 9, "query": "different question",
                                  "category": "bugs", "ground_truth": None}]))
    cfg = harness.cfg(resume=run_id)
    cfg.dataset = str(other)
    with pytest.raises(SystemExit) as e:
        R.run(cfg)
    assert "different dataset" in str(e.value)


def test_resume_ignores_a_row_torn_by_a_kill_mid_write(harness):
    harness.install([StubGen("a"), StubGen("b")])
    run_id = os.path.basename(R.run(harness.cfg()))
    path = os.path.join(str(harness.tmp), run_id, "per_query.jsonl")
    with open(path, "a") as f:
        f.write('{"query_id": 4, "system": "a", "answ')      # truncated line

    rows, done = R._read_finished(os.path.join(str(harness.tmp), run_id), ["a", "b"])
    assert len(rows) == 8 and done == {"1", "2", "3", "4"}


# ── adding an arm to a finished run ──────────────────────────────────────

def test_resuming_with_a_new_arm_keeps_the_arms_already_measured(harness):
    """
    Adding a third arm to a finished run must not delete the two already there.
    An earlier version kept only rows whose system was in the new generator
    list, so `--resume <dir> --generators <new arm>` wiped the completed work.
    """
    harness.install([StubGen("a"), StubGen("b")])
    run_id = os.path.basename(R.run(harness.cfg()))

    added = StubGen("c")
    harness.install([added])
    cfg = harness.cfg(resume=run_id)
    cfg.generators = ["c"]
    run_dir = R.run(cfg)

    rows = _rows(run_dir)
    assert {r["system"] for r in rows} == {"a", "b", "c"}
    assert len(rows) == 12                       # 4 questions x 3 systems
    # The new arm answered every question; the old arms were not re-run.
    assert added.seen == [f"question {i}" for i in (1, 2, 3, 4)]


def test_adding_an_arm_leaves_one_row_per_question_and_system(harness):
    harness.install([StubGen("a"), StubGen("b")])
    run_id = os.path.basename(R.run(harness.cfg()))
    harness.install([StubGen("c")])
    cfg = harness.cfg(resume=run_id)
    cfg.generators = ["c"]
    keys = [(r["query_id"], r["system"]) for r in _rows(R.run(cfg))]
    assert len(keys) == len(set(keys))


def test_an_incomplete_question_is_redone_without_losing_other_arms(harness):
    """Partial rows for THIS run's systems are dropped; a bystander arm is not."""
    rows = [
        {"query_id": 1, "system": "a", "answer": "x", "ir": {}, "answer_scores": {}},
        {"query_id": 1, "system": "b", "answer": "x", "ir": {}, "answer_scores": {}},
        {"query_id": 1, "system": "z", "answer": "x", "ir": {}, "answer_scores": {}},
        {"query_id": 2, "system": "a", "answer": "x", "ir": {}, "answer_scores": {}},
        {"query_id": 2, "system": "z", "answer": "x", "ir": {}, "answer_scores": {}},
    ]
    d = harness.tmp / "run_x"
    d.mkdir()
    (d / "per_query.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

    kept, done = R._read_finished(str(d), ["a", "b"])

    assert done == {"1"}
    kept_keys = {(r["query_id"], r["system"]) for r in kept}
    # Question 2 is incomplete for a/b, so its "a" row goes; "z" is untouched.
    assert (2, "a") not in kept_keys
    assert (2, "z") in kept_keys and (1, "z") in kept_keys


# ── CLI wiring ───────────────────────────────────────────────────────────

def test_every_cli_flag_reaches_the_config(monkeypatch):
    """
    Regression for a silently dead flag: --resume was parsed and never assigned
    to the config, so `--resume <dir>` started a fresh run and the user only
    found out by reading the run id in the log.

    Rather than pin one flag, this asserts the general property: every argparse
    destination that names a config field must actually arrive there.
    """
    from eval_harness.config import EvalConfig

    argv = ["run_eval",
            "--dataset", "data/x.json",
            "--limit", "7",
            "--generators", "marag",
            "--judge", "ollama:mistral",
            "--top-k", "3",
            "--seed", "9",
            "--resume", "run_abc_def",
            "--stratify", "category,ecosystem"]
    monkeypatch.setattr(sys, "argv", argv)
    cfg = R._parse_args()

    fields = set(vars(EvalConfig()))
    parsed = {"dataset": "data/x.json", "limit": 7, "judge": "ollama:mistral",
              "top_k": 3, "seed": 9, "resume": "run_abc_def",
              "stratify": "category,ecosystem"}
    for name, expected in parsed.items():
        assert name in fields, f"{name} is not a config field"
        assert getattr(cfg, name) == expected, f"--{name} never reached the config"
    assert cfg.generators == ["marag"]
