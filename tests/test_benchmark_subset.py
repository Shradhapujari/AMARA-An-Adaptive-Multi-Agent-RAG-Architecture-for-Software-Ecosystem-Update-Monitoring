"""
Tests for build_benchmark_subset.py — the stratified subset of benchmark_300.

The defect these guard against is using a prefix (`--limit N`) as a sample.
benchmark_300.json is emitted grouped by ecosystem and category, so its first
100 records hold two of five categories; a per-category table built from that
prefix silently omits security, community, and general.
"""

import collections
import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "build_benchmark_subset", os.path.join(ROOT, "build_benchmark_subset.py"))
bbs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bbs)


def _synthetic(n_per_cell=6):
    """Parent-shaped records: 5 categories x 4 ecosystems, some with gt."""
    recs, rid = [], 0
    for cat in ["bugs", "community", "general", "releases", "security"]:
        for eco in ["apple_ios", "fedora", "firefox", "ubuntu"]:
            for j in range(n_per_cell):
                rid += 1
                recs.append({
                    "id": rid, "query": f"q{rid}", "category": cat,
                    "ecosystem": eco, "source": "mined_reddit_title",
                    "ground_truth": f"gt{rid}" if j == 0 else None,
                })
    return recs


@pytest.fixture(scope="module")
def parent():
    p = os.path.join(ROOT, "data", "benchmark_300.json")
    if not os.path.exists(p):
        pytest.skip("data/benchmark_300.json not present")
    return json.load(open(p))


# ── the defect ───────────────────────────────────────────────────────────

def test_prefix_of_the_parent_is_not_a_sample(parent):
    """Documents why this module exists: --limit 100 covers 2 of 5 categories."""
    prefix_cats = {r["category"] for r in parent[:100]}
    assert len(prefix_cats) < 5


def test_subset_covers_every_category_evenly(parent):
    subset = bbs.select(parent, 100)
    counts = collections.Counter(r["category"] for r in subset)
    assert len(subset) == 100
    assert set(counts.values()) == {20}


# ── selection properties ─────────────────────────────────────────────────

def test_selection_is_deterministic():
    recs = _synthetic()
    assert [r["id"] for r in bbs.select(recs, 40)] == [r["id"] for r in bbs.select(recs, 40)]


def test_records_are_copied_verbatim(parent):
    """A subset row must stay auditable against its parent row."""
    by_id = {r["id"]: r for r in parent}
    for r in bbs.select(parent, 50):
        assert r == by_id[r["id"]]


def test_ecosystems_are_spread_not_clustered():
    recs = _synthetic()
    subset = bbs.select(recs, 40)          # 8 per category over 4 ecosystems
    per_cell = collections.Counter((r["category"], r["ecosystem"]) for r in subset)
    assert set(per_cell.values()) == {2}   # round-robin, not 8 from one ecosystem


def test_ground_truth_bearing_records_are_preferred():
    recs = _synthetic()
    subset = bbs.select(recs, 20)          # 4 per category, 1 per ecosystem
    # Every cell's gt record is its first candidate, so all picks carry gt.
    assert all(r["ground_truth"] for r in subset)


def test_ground_truth_share_is_not_diluted(parent):
    subset = bbs.select(parent, 100)
    p_share = sum(1 for r in parent if r.get("ground_truth")) / len(parent)
    s_share = sum(1 for r in subset if r.get("ground_truth")) / len(subset)
    assert s_share >= p_share


def test_uneven_n_spreads_the_remainder():
    recs = _synthetic()
    counts = collections.Counter(r["category"] for r in bbs.select(recs, 22))
    assert sum(counts.values()) == 22
    assert max(counts.values()) - min(counts.values()) <= 1


def test_request_larger_than_a_category_reports_and_returns_what_exists(capsys):
    recs = [r for r in _synthetic(n_per_cell=1) if r["category"] == "bugs"]  # 4 records
    subset = bbs.select(recs, 10)
    assert len(subset) == 4
    assert "only 4 of 10 available" in capsys.readouterr().out


# ── the emitted file matches what the builder promises ───────────────────

def test_emitted_subset_and_manifest_agree():
    sub_p = os.path.join(ROOT, "data", "benchmark_100.json")
    man_p = os.path.join(ROOT, "data", "benchmark_100.manifest.json")
    if not (os.path.exists(sub_p) and os.path.exists(man_p)):
        pytest.skip("data/benchmark_100.json not built")
    subset, man = json.load(open(sub_p)), json.load(open(man_p))
    assert man["n"] == len(subset)
    assert man["ids"] == [r["id"] for r in subset]
    assert man["categories"] == dict(sorted(
        collections.Counter(r["category"] for r in subset).items()))
    assert man["with_ground_truth"] == sum(1 for r in subset if r.get("ground_truth"))
