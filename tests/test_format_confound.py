"""
Tests for analyze_format_confound.py — the retrieval/format decomposition.

The analysis only means anything if the two multi-agent arms really do share a
retrieval path, so `retrieval_identical` is the load-bearing check: it is what
licenses reading `marag_llm - marag` as a pure format effect. The rest is
paired arithmetic that must not silently skip questions or count a tie as a win.
"""

import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "analyze_format_confound", os.path.join(ROOT, "analyze_format_confound.py"))
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)


def _row(qid, system, docs, faith=None, answer="x"):
    return {"query_id": qid, "system": system, "doc_ids": docs, "answer": answer,
            "answer_scores": ({"faithfulness": faith} if faith is not None else {})}


def _by(rows):
    out = {}
    for r in rows:
        out.setdefault(r["query_id"], {})[r["system"]] = r
    return out


# ── retrieval identity ───────────────────────────────────────────────────

def test_identical_ranked_docs_are_counted_only_when_order_matches():
    by = _by([_row(1, "marag", ["a", "b"]), _row(1, "marag_llm", ["a", "b"]),
              _row(2, "marag", ["a", "b"]), _row(2, "marag_llm", ["b", "a"])])
    assert A.retrieval_identical(by, "marag", "marag_llm") == (1, 2)


def test_questions_missing_an_arm_are_not_counted():
    by = _by([_row(1, "marag", ["a"]), _row(1, "marag_llm", ["a"]),
              _row(2, "marag", ["a"])])
    assert A.retrieval_identical(by, "marag", "marag_llm") == (1, 1)


# ── paired deltas ────────────────────────────────────────────────────────

def test_paired_delta_reports_direction_and_win_tie_loss():
    by = _by([_row(1, "x", [], faith=0.9), _row(1, "y", [], faith=0.5),
              _row(2, "x", [], faith=0.5), _row(2, "y", [], faith=0.5),
              _row(3, "x", [], faith=0.1), _row(3, "y", [], faith=0.6)])
    d = A.paired_delta(by, "x", "y", "faithfulness")
    assert d["n"] == 3
    assert d["wins"] == 1 and d["ties"] == 1 and d["losses"] == 1
    assert d["mean"] == pytest.approx((0.4 + 0.0 - 0.5) / 3)


def test_a_question_scored_for_only_one_arm_is_dropped_not_zero_filled():
    by = _by([_row(1, "x", [], faith=0.9), _row(1, "y", [], faith=0.5),
              _row(2, "x", [], faith=0.9), _row(2, "y", [])])
    d = A.paired_delta(by, "x", "y", "faithfulness")
    assert d["n"] == 1 and d["mean"] == pytest.approx(0.4)


def test_paired_delta_on_an_absent_metric_reports_nothing_rather_than_zero():
    by = _by([_row(1, "x", []), _row(1, "y", [])])
    assert A.paired_delta(by, "x", "y", "faithfulness") == {"n": 0}


# ── offsetting relevant documents ────────────────────────────────────────

def test_unique_relevant_counts_only_judged_relevant_differences():
    by = _by([_row(1, "marag", ["a", "b"]), _row(1, "single_agent", ["a", "c"])])
    qrels = {"1": {"a": 2, "b": 1, "c": 0}}          # b relevant, c not
    a_only, b_only, differing = A.unique_relevant(by, qrels, "marag", "single_agent")
    assert (a_only, b_only, differing) == (1, 0, 2)


def test_offsetting_uniques_are_visible_even_when_totals_tie():
    """The point of the check: equal counts, different documents."""
    by = _by([_row(1, "marag", ["a"]), _row(1, "single_agent", ["b"])])
    qrels = {"1": {"a": 2, "b": 2}}
    a_only, b_only, _ = A.unique_relevant(by, qrels, "marag", "single_agent")
    assert a_only == b_only == 1


def test_unjudged_documents_count_as_not_relevant():
    by = _by([_row(1, "marag", ["a"]), _row(1, "single_agent", ["z"])])
    a_only, b_only, differing = A.unique_relevant(by, {}, "marag", "single_agent")
    assert (a_only, b_only, differing) == (0, 0, 2)


# ── rendering ────────────────────────────────────────────────────────────

def test_report_runs_over_a_written_run_dir(tmp_path):
    rows = [_row(1, "marag", ["a"], 0.5, "a" * 2000),
            _row(1, "marag_llm", ["a"], 0.9, "short"),
            _row(1, "single_agent", ["b"], 0.9, "short")]
    (tmp_path / "per_query.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows))
    (tmp_path / "qrels.json").write_text(json.dumps({"1": {"a": 2, "b": 2}}))

    text = A.report(str(tmp_path))
    assert "identical ranked doc_ids: **1/1**" in text
    assert "format alone" in text
    assert "| `marag` | 2000 | 2000 |" in text


def test_answer_lengths_reports_nothing_for_an_absent_arm():
    assert A.answer_lengths(_by([_row(1, "marag", [])]), "nope") == {}
