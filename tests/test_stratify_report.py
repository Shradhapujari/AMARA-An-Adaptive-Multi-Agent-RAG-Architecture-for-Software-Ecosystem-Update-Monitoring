"""
Tests for run_eval.stratify_summary — the line the harness prints to show what
a stratified selection actually produced.

`--stratify` accepts a composite key ("category,ecosystem"). The reporting line
looked the whole key up as a single field, so `r.get("category,ecosystem")`
returned None for every record and the harness printed `None=100`: a line that
reads as a successful stratification while carrying no information.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness.run_eval import stratify_summary  # noqa: E402


def _recs(pairs):
    return [{"category": c, "ecosystem": e} for c, e in pairs]


def test_single_field_lists_its_mix():
    out = stratify_summary(_recs([("releases", "x"), ("bugs", "x"), ("bugs", "y")]),
                           "category")
    assert out == "category: bugs=2, releases=1"


def test_composite_key_reports_each_field_separately():
    out = stratify_summary(_recs([("releases", "x"), ("releases", "y"),
                                  ("bugs", "x"), ("bugs", "y")]),
                           "category,ecosystem")
    assert out == "category: bugs=2, releases=2; ecosystem: x=2, y=2"


def test_composite_key_never_reports_a_single_none_bucket():
    """The defect: one dict lookup of the whole key yields None for every row."""
    out = stratify_summary(_recs([("releases", "x"), ("bugs", "y")]),
                           "category,ecosystem")
    assert "None" not in out


def test_many_valued_field_is_summarised_by_spread_not_listed():
    recs = _recs([("releases", f"eco{i}") for i in range(21)])
    out = stratify_summary(recs, "ecosystem")
    assert out == "ecosystem: 21 distinct, 1-1 each"


def test_spread_shows_imbalance():
    recs = _recs([("releases", "a")] * 5 + [("releases", f"eco{i}") for i in range(9)])
    out = stratify_summary(recs, "ecosystem")
    assert out == "ecosystem: 10 distinct, 1-5 each"


def test_missing_field_is_visible_rather_than_silently_dropped():
    out = stratify_summary([{"category": "bugs"}, {"category": "bugs"}],
                           "category,ecosystem")
    assert out == "category: bugs=2; ecosystem: None=2"


def test_empty_or_blank_key_falls_back_to_category():
    recs = _recs([("bugs", "x")])
    assert stratify_summary(recs, "") == "category: bugs=1"
    assert stratify_summary(recs, " , ") == "category: bugs=1"
