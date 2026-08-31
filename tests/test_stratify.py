"""
Tests for `stratified_limit` — the sampler behind `--limit`.

`data/benchmark_300.json` is written as five contiguous 60-question category
blocks, each internally ordered by ecosystem, so a head slice silently reports
a two-category subset as if it were the benchmark. These tests pin the two
properties that make the sampler safe to trust:

  * balance is preserved on every named field at the same time, and
  * a smaller limit is a strict prefix of a larger one, so `--resume` of a
    partial run stays valid.

The second property is what makes the first one non-obvious: it rules out
shuffling, so balance has to come from the walk order.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness.benchmarks import stratified_limit  # noqa: E402


def make_records(categories, ecosystems, per_cell=4):
    """Blocked like the real file: category blocks, ecosystem-ordered within."""
    out, i = [], 0
    for cat in categories:
        for eco in ecosystems:
            for _ in range(per_cell):
                i += 1
                out.append({"id": i, "category": cat, "ecosystem": eco,
                            "query": f"q{i}"})
    return out


CATS = ["releases", "bugs", "security", "community", "general"]
ECOS = ["ios", "android", "windows", "ubuntu", "firefox", "docker"]


def test_head_slice_would_collapse_categories():
    """Establishes the problem the sampler exists to solve."""
    recs = make_records(CATS, ECOS)
    head = recs[:30]
    # 24 records per category block, so a 30-slice reaches only into the second.
    assert len({r["category"] for r in head}) == 2
    assert len(stratified_limit(recs, 30, key="category")) == 30
    assert len({r["category"] for r in stratified_limit(recs, 30, key="category")}) == len(CATS)


def test_single_field_preserves_that_field():
    recs = make_records(CATS, ECOS)
    sel = stratified_limit(recs, 30, key="category")
    assert len(sel) == 30
    assert len({r["category"] for r in sel}) == len(CATS)


def test_two_fields_preserve_both_dimensions():
    """The regression: tuple-grouping balanced ecosystem by sacrificing category.

    A flat round-robin over the (category, ecosystem) cross product has
    len(CATS)*len(ECOS) groups, so a small limit never reaches the later
    categories. Balance on the first field must not degrade when a second is
    added.
    """
    recs = make_records(CATS, ECOS)
    sel = stratified_limit(recs, 30, key="category,ecosystem")
    assert len(sel) == 30
    assert len({r["category"] for r in sel}) == len(CATS)
    assert len({r["ecosystem"] for r in sel}) > 1


def test_two_fields_beat_one_on_the_secondary_field():
    recs = make_records(CATS, ECOS)
    one = stratified_limit(recs, 60, key="category")
    two = stratified_limit(recs, 60, key="category,ecosystem")
    assert (len({r["ecosystem"] for r in two})
            > len({r["ecosystem"] for r in one}))
    # ...without giving up the primary field.
    assert len({r["category"] for r in two}) == len(CATS)


@pytest.mark.parametrize("key", ["category", "category,ecosystem"])
def test_smaller_limit_is_a_prefix_of_a_larger_one(key):
    """Resume safety: a partial run's rows stay the first rows of a full run."""
    recs = make_records(CATS, ECOS)
    small = stratified_limit(recs, 12, key=key)
    large = stratified_limit(recs, 40, key=key)
    assert [r["id"] for r in large[:12]] == [r["id"] for r in small]


@pytest.mark.parametrize("key", ["category", "category,ecosystem"])
def test_selection_is_deterministic(key):
    recs = make_records(CATS, ECOS)
    a = stratified_limit(recs, 25, key=key)
    b = stratified_limit(recs, 25, key=key)
    assert [r["id"] for r in a] == [r["id"] for r in b]


def test_no_record_is_returned_twice():
    recs = make_records(CATS, ECOS)
    sel = stratified_limit(recs, 77, key="category,ecosystem")
    ids = [r["id"] for r in sel]
    assert len(ids) == len(set(ids))


def test_limit_at_or_above_size_returns_everything():
    recs = make_records(CATS, ECOS, per_cell=1)
    assert len(stratified_limit(recs, len(recs), key="category")) == len(recs)
    assert len(stratified_limit(recs, len(recs) + 10, key="category")) == len(recs)


def test_non_positive_limit_returns_everything():
    recs = make_records(CATS, ECOS, per_cell=1)
    assert len(stratified_limit(recs, 0, key="category")) == len(recs)
    assert len(stratified_limit(recs, -5, key="category")) == len(recs)


def test_uneven_groups_degrade_gracefully():
    """A group that runs out stops contributing; the rest keep filling."""
    recs = ([{"id": 1, "category": "a"}]
            + [{"id": i, "category": "b"} for i in range(2, 12)])
    sel = stratified_limit(recs, 6, key="category")
    assert len(sel) == 6
    assert sum(1 for r in sel if r["category"] == "a") == 1


def test_missing_field_is_its_own_group_rather_than_an_error():
    recs = [{"id": 1, "category": "a"}, {"id": 2}, {"id": 3, "category": "a"}]
    sel = stratified_limit(recs, 2, key="category")
    assert len(sel) == 2
    assert {r["id"] for r in sel} == {1, 2}


def test_unknown_field_name_yields_one_group_not_a_crash():
    recs = make_records(CATS, ECOS, per_cell=1)
    sel = stratified_limit(recs, 5, key="nope")
    assert len(sel) == 5


def test_empty_key_falls_back_to_category():
    recs = make_records(CATS, ECOS)
    sel = stratified_limit(recs, 20, key="")
    assert len({r["category"] for r in sel}) == len(CATS)


def test_real_benchmark_file_keeps_all_five_categories_at_every_limit():
    """Guards the actual artifact, not just a synthetic fixture."""
    import json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "benchmark_300.json")
    if not os.path.exists(path):
        pytest.skip("benchmark_300.json not built")
    recs = json.load(open(path))
    for limit in (10, 30, 100, 150):
        sel = stratified_limit(recs, limit, key="category,ecosystem")
        assert len(sel) == limit
        assert len({r["category"] for r in sel}) == 5, f"limit={limit}"
