"""
Tests for merge_arm.py — joining an arm measured in a separate run.

The tool's value is entirely in what it refuses. Merging an arm that saw a
different corpus, a different judge, or a different question set produces a
table whose columns are not comparable while looking exactly like one whose
columns are, so every guard is pinned here.
"""

import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "merge_arm", os.path.join(ROOT, "merge_arm.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def _mkrun(tmp_path, name, rows, cfg=None):
    d = tmp_path / name
    d.mkdir()
    (d / "per_query.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    if cfg is not None:
        (d / "config.json").write_text(json.dumps(cfg))
    return str(d)


def _row(qid, system, docs=("a", "b")):
    return {"query_id": qid, "system": system, "doc_ids": list(docs),
            "answer": "x", "ir": {}, "answer_scores": {}, "latency_s": 1.0}


CFG = {"judge": "ollama:llama3.1", "corpus": {"mode": "replay"}, "ks": [1],
       "systems_evaluated": ["marag", "single_agent"]}


@pytest.fixture
def runs(tmp_path):
    target = _mkrun(tmp_path, "run_1_hashAAA",
                    [_row(1, "marag"), _row(1, "single_agent"),
                     _row(2, "marag"), _row(2, "single_agent")], CFG)
    source = _mkrun(tmp_path, "run_2_hashAAA",
                    [_row(1, "marag_llm"), _row(2, "marag_llm")], CFG)
    return target, source


# ── the happy path ───────────────────────────────────────────────────────

def test_comparable_runs_merge(runs):
    target, source = runs
    assert M.check(target, source, "marag_llm", "marag") == []
    n = M.merge(target, source, "marag_llm", "marag")
    assert n == 2
    systems = {r["system"] for r in M._rows(target)}
    assert systems == {"marag", "single_agent", "marag_llm"}


def test_merge_backs_up_before_writing(runs):
    target, source = runs
    M.merge(target, source, "marag_llm", "marag")
    assert os.path.exists(os.path.join(target, "per_query.jsonl.before_merge"))


def test_merge_records_provenance_in_the_config(runs):
    target, source = runs
    M.merge(target, source, "marag_llm", "marag")
    cfg = json.load(open(os.path.join(target, "config.json")))
    assert "marag_llm" in cfg["systems_evaluated"]
    assert cfg["merged_arms"][0]["arm"] == "marag_llm"
    assert cfg["merged_arms"][0]["from"] == "run_2_hashAAA"


# ── the refusals ─────────────────────────────────────────────────────────

def test_refuses_a_different_dataset(tmp_path):
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag")], CFG)
    source = _mkrun(tmp_path, "run_2_hashBBB", [_row(1, "marag_llm")], CFG)
    assert any("different datasets" in p
               for p in M.check(target, source, "marag_llm"))


def test_refuses_a_different_judge(tmp_path):
    other = dict(CFG, judge="ollama:qwen2.5:7b-instruct")
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag")], CFG)
    source = _mkrun(tmp_path, "run_2_hashAAA", [_row(1, "marag_llm")], other)
    assert any("different judges" in p for p in M.check(target, source, "marag_llm"))


def test_refuses_a_different_corpus_mode(tmp_path):
    live = dict(CFG, corpus={"mode": "live"})
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag")], CFG)
    source = _mkrun(tmp_path, "run_2_hashAAA", [_row(1, "marag_llm")], live)
    assert any("different corpus mode" in p
               for p in M.check(target, source, "marag_llm"))


def test_refuses_when_retrieval_does_not_match_the_reference_arm(tmp_path):
    """The check that licenses calling a difference an answer-side effect."""
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag", ("a", "b"))], CFG)
    source = _mkrun(tmp_path, "run_2_hashAAA",
                    [_row(1, "marag_llm", ("a", "z"))], CFG)
    problems = M.check(target, source, "marag_llm", "marag")
    assert any("retrieval differs" in p for p in problems)


def test_refuses_an_incomplete_arm(tmp_path):
    target = _mkrun(tmp_path, "run_1_hashAAA",
                    [_row(1, "marag"), _row(2, "marag")], CFG)
    source = _mkrun(tmp_path, "run_2_hashAAA", [_row(1, "marag_llm")], CFG)
    assert any("question sets differ" in p
               for p in M.check(target, source, "marag_llm"))


def test_refuses_an_arm_already_present(runs):
    target, source = runs
    M.merge(target, source, "marag_llm", "marag")
    assert any("already has arm" in p for p in M.check(target, source, "marag_llm"))


def test_refuses_when_the_source_lacks_the_arm(runs):
    target, source = runs
    assert any("no rows for arm" in p for p in M.check(target, source, "nope"))


def test_refusal_writes_nothing(tmp_path):
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag")], CFG)
    source = _mkrun(tmp_path, "run_2_hashBBB", [_row(1, "marag_llm")], CFG)
    before = open(os.path.join(target, "per_query.jsonl")).read()
    with pytest.raises(SystemExit):
        M.merge(target, source, "marag_llm")
    assert open(os.path.join(target, "per_query.jsonl")).read() == before
    assert not os.path.exists(os.path.join(target, "per_query.jsonl.before_merge"))


def test_force_merges_but_still_names_every_problem(tmp_path, capsys):
    live = dict(CFG, corpus={"mode": "live"})
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag")], CFG)
    source = _mkrun(tmp_path, "run_2_hashAAA", [_row(1, "marag_llm")], live)
    M.merge(target, source, "marag_llm", force=True)
    assert "WARNING (forced): different corpus mode" in capsys.readouterr().out


def test_merging_into_a_file_without_a_trailing_newline(tmp_path):
    """
    Appending to a file whose last line is unterminated concatenated the first
    merged row onto it, so the joined line was not JSON and the row was lost.
    """
    target = _mkrun(tmp_path, "run_1_hashAAA", [_row(1, "marag")], CFG)
    path = os.path.join(target, "per_query.jsonl")
    assert not open(path).read().endswith("\n")      # the fixture's shape
    source = _mkrun(tmp_path, "run_2_hashAAA", [_row(1, "marag_llm")], CFG)

    M.merge(target, source, "marag_llm", "marag")

    rows = M._rows(target)                            # parses => no torn line
    assert [r["system"] for r in rows] == ["marag", "marag_llm"]
