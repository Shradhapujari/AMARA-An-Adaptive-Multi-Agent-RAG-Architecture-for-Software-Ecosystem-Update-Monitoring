"""
Tests for thin-sample rendering in eval_harness/report.py.

The defect, observed on a real 100-question run: `correctness` was computed on
1-2 questions (only those carried ground truth), and the report rendered

    | marag_llm | ... | 1.000±0.000 | ... |

which reads as a perfect score measured with certainty. Nothing in the table
said n=1. A cell whose sample cannot support a CI must not print one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness import report as R  # noqa: E402


def _agg(systems):
    return {"systems": systems, "by_category": {}, "ir_keys": ["mrr"],
            "answer_keys": ["faithfulness", "correctness"]}


CFG = {"dataset": "d.json", "n_questions": 100, "dataset_hash": "abc",
       "judge": "ollama:llama3.1", "judge_active": True,
       "systems_evaluated": ["a"], "seed": 42, "top_k": 4}


# ── the cell formatter ───────────────────────────────────────────────────

def test_full_sample_renders_mean_and_ci():
    assert R._fmt((0.885, 0.06, 100), 100) == "0.885±0.060"


def test_single_observation_never_prints_a_confidence_interval():
    """The defect: n=1 gives ci=0.000, which reads as certainty."""
    out = R._fmt((1.0, 0.0, 1), 100)
    assert "±" not in out
    assert out == "1.000 (n=1, too few)"


def test_below_threshold_is_labelled_too_few():
    assert R._fmt((0.75, 0.49, 2), 100) == "0.750 (n=2, too few)"
    assert R._fmt((0.5, 0.1, R.MIN_REPORTABLE_N - 1), 100).endswith("too few)")


def test_partial_sample_at_or_above_threshold_keeps_ci_but_shows_n():
    assert R._fmt((0.5, 0.1, 28), 100) == "0.500±0.100 (n=28)"


def test_at_threshold_is_reportable():
    assert R._fmt((0.5, 0.1, R.MIN_REPORTABLE_N), 100) == "0.500±0.100 (n=5)"


def test_missing_and_empty_cells_render_as_a_dash():
    assert R._fmt(None, 100) == "—"
    assert R._fmt((0.0, 0.0, 0), 100) == "—"


def test_no_expected_count_means_no_n_suffix():
    """Without a denominator, a full-looking cell is not annotated."""
    assert R._fmt((0.9, 0.05, 40)) == "0.900±0.050"


# ── the rendered report ──────────────────────────────────────────────────

def test_report_flags_thin_columns_with_a_footnote(tmp_path):
    agg = _agg({"a": {"mrr": (0.9, 0.05, 100),
                      "faithfulness": (0.7, 0.04, 100),
                      "correctness": (1.0, 0.0, 1),
                      "latency_s": (20.0, 0.0, 100)}})
    path = str(tmp_path / "report.md")
    R.write_markdown(agg, CFG, path)
    text = open(path).read()

    assert "1.000 (n=1, too few)" in text
    assert "1.000±0.000" not in text
    assert "cells carrying `(n=...)`" in text


def test_report_omits_the_footnote_when_every_cell_is_full(tmp_path):
    agg = _agg({"a": {"mrr": (0.9, 0.05, 100),
                      "faithfulness": (0.7, 0.04, 100),
                      "latency_s": (20.0, 0.0, 100)}})
    path = str(tmp_path / "report.md")
    R.write_markdown(agg, CFG, path)
    assert "cells carrying" not in open(path).read()


def test_expected_count_comes_from_latency_which_every_question_records():
    assert R._expected_n({"latency_s": (20.0, 0.0, 100)}) == 100
    assert R._expected_n({}) == 0
