"""Offline structural tests for the multi-ecosystem benchmark.

These assert the *shape and balance* of data/benchmark_300.json, which is the
whole point of the file: table_50_questions.json was Reddit-only and skewed
(general 26 / releases 11 / bugs 9 / community 4), so the value of the larger
set is that it is stratified and that every question's provenance is declared.

Nothing here touches the network. `test_no_network_needed` proves it by
poisoning the socket layer while the dataset is loaded.
"""
from __future__ import annotations

import json
import os
import re
import socket

import pytest

from eval_harness.config import ROOT
from eval_harness.dataset import load_dataset

BENCHMARK_REL = os.path.join("data", "benchmark_300.json")
BENCHMARK = os.path.join(ROOT, BENCHMARK_REL)
MANIFEST = os.path.join(ROOT, "data", "benchmark_300.manifest.json")

EXPECTED_TOTAL = 300
EXPECTED_CATEGORIES = {"releases", "bugs", "security", "community", "general"}
MIN_SHARE, MAX_SHARE = 0.10, 0.30
MIN_ECOSYSTEMS = 15
VALID_SOURCES = {"mined_reddit_title", "mined_release_record", "backfill_template"}


@pytest.fixture(scope="module")
def records():
    if not os.path.exists(BENCHMARK):
        pytest.fail(
            f"{BENCHMARK_REL} is missing. Build it with:\n"
            f"    python build_multiecosystem_benchmark.py")
    with open(BENCHMARK) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def manifest():
    if not os.path.exists(MANIFEST):
        pytest.skip("manifest not generated")
    with open(MANIFEST) as f:
        return json.load(f)


class TestSize:
    def test_is_a_list_of_300(self, records):
        assert isinstance(records, list)
        assert len(records) == EXPECTED_TOTAL

    def test_ids_are_unique(self, records):
        ids = [r["id"] for r in records]
        assert len(set(ids)) == EXPECTED_TOTAL

    def test_ids_are_contiguous_from_one(self, records):
        assert sorted(r["id"] for r in records) == list(range(1, EXPECTED_TOTAL + 1))

    def test_no_duplicate_queries(self, records):
        queries = [r["query"] for r in records]
        dupes = {q for q in queries if queries.count(q) > 1}
        assert not dupes, f"duplicate queries: {sorted(dupes)[:5]}"

    def test_no_near_duplicate_queries(self, records):
        """Case/punctuation-insensitive duplicates would inflate the count."""
        norm = [re.sub(r"[^a-z0-9]+", " ", r["query"].lower()).strip()
                for r in records]
        assert len(set(norm)) == EXPECTED_TOTAL


class TestCategoryStratification:
    def test_only_expected_categories(self, records):
        assert {r["category"] for r in records} == EXPECTED_CATEGORIES

    @pytest.mark.parametrize("category", sorted(EXPECTED_CATEGORIES))
    def test_category_share_within_band(self, records, category):
        share = sum(1 for r in records if r["category"] == category) / len(records)
        assert MIN_SHARE <= share <= MAX_SHARE, (
            f"{category} is {share:.1%}, outside the "
            f"{MIN_SHARE:.0%}-{MAX_SHARE:.0%} band")

    def test_is_more_balanced_than_the_50_question_set(self, records):
        """The old set's largest category was 52% of the file."""
        counts = [sum(1 for r in records if r["category"] == c)
                  for c in EXPECTED_CATEGORIES]
        assert max(counts) / len(records) < 0.52


class TestEcosystemCoverage:
    def test_enough_distinct_ecosystems(self, records):
        ecosystems = {r["ecosystem"] for r in records}
        assert len(ecosystems) >= MIN_ECOSYSTEMS, sorted(ecosystems)

    def test_enough_distinct_vendors(self, records):
        vendors = {r["vendor"] for r in records}
        assert len(vendors) >= MIN_ECOSYSTEMS, sorted(vendors)

    def test_no_ecosystem_dominates(self, records):
        for eco in {r["ecosystem"] for r in records}:
            share = sum(1 for r in records if r["ecosystem"] == eco) / len(records)
            assert share <= 0.20, f"{eco} is {share:.1%} of the benchmark"

    def test_every_ecosystem_has_a_meaningful_slice(self, records):
        for eco in {r["ecosystem"] for r in records}:
            n = sum(1 for r in records if r["ecosystem"] == eco)
            assert n >= 5, f"{eco} only has {n} questions"

    @pytest.mark.parametrize("expected", [
        "Apple iOS", "Apple macOS", "Android", "Microsoft Windows", "Ubuntu",
        "Debian", "Fedora / RHEL", "Arch Linux", "Mozilla Firefox",
        "Google Chrome", "Docker", "Kubernetes", "npm / Node.js",
        "pip / Python", "cargo / Rust", "Home Assistant / smart home",
        "NAS / self-hosted", "WordPress", "PostgreSQL", "MySQL / SQL",
        "LLM / AI models",
    ])
    def test_required_ecosystem_is_present(self, records, expected):
        """The roadmap item names these ecosystems explicitly."""
        assert any(r["vendor"] == expected for r in records)

    def test_each_ecosystem_spans_several_categories(self, records):
        for eco in {r["ecosystem"] for r in records}:
            cats = {r["category"] for r in records if r["ecosystem"] == eco}
            assert len(cats) >= 3, f"{eco} only covers {sorted(cats)}"


class TestRecordShape:
    REQUIRED = ["id", "query", "category", "ecosystem", "vendor", "reddit_id",
                "url", "source", "source_endpoint", "source_id", "mined",
                "subreddit", "date", "ground_truth", "context"]

    def test_required_keys_present(self, records):
        for r in records:
            missing = [k for k in self.REQUIRED if k not in r]
            assert not missing, f"record {r.get('id')} missing {missing}"

    def test_queries_are_non_trivial_strings(self, records):
        for r in records:
            assert isinstance(r["query"], str)
            q = r["query"].strip()
            assert q == r["query"], f"record {r['id']} query has stray whitespace"
            assert 15 <= len(q) <= 200, f"record {r['id']} query length {len(q)}"
            assert "\n" not in q

    def test_ids_are_ints(self, records):
        assert all(isinstance(r["id"], int) for r in records)


class TestProvenanceHonesty:
    """Mined and templated questions must stay distinguishable."""

    def test_source_values_are_known(self, records):
        assert {r["source"] for r in records} <= VALID_SOURCES

    def test_mined_flag_matches_source(self, records):
        for r in records:
            expected = r["source"] != "backfill_template"
            assert r["mined"] is expected, f"record {r['id']} mined/source disagree"

    def test_mined_records_cite_a_live_source(self, records):
        for r in records:
            if not r["mined"]:
                continue
            assert r["source_id"], f"record {r['id']} is mined but has no source_id"
            assert str(r["source_endpoint"]).startswith("/api/"), (
                f"record {r['id']} endpoint {r['source_endpoint']!r}")

    def test_reddit_records_carry_a_reddit_id(self, records):
        for r in records:
            if r["source"] == "mined_reddit_title":
                assert r["reddit_id"], f"record {r['id']} has no reddit_id"
                assert r["reddit_id"] == r["source_id"]
                assert r["subreddit"], f"record {r['id']} has no subreddit"

    def test_release_records_carry_ground_truth(self, records):
        rel = [r for r in records if r["source"] == "mined_release_record"]
        for r in rel:
            assert r["ground_truth"], f"record {r['id']} has no ground truth"
            assert r["reddit_id"] is None

    def test_backfilled_records_declare_why(self, records):
        for r in records:
            if r["source"] == "backfill_template":
                assert r.get("backfill_reason"), (
                    f"record {r['id']} is templated but gives no reason")
                assert r["source_id"] is None

    def test_no_ground_truth_is_fabricated_for_reddit_rows(self, records):
        """Reddit titles have no authoritative answer, so none is invented."""
        for r in records:
            if r["source"] == "mined_reddit_title":
                assert r["ground_truth"] is None

    def test_majority_of_questions_are_mined(self, records):
        mined = sum(1 for r in records if r["mined"])
        assert mined / len(records) >= 0.80, (
            f"only {mined}/{len(records)} questions were mined from live data")

    def test_release_api_is_actually_exercised(self, records):
        """Guards the regression where Reddit crowded the version API out."""
        n = sum(1 for r in records if r["source"] == "mined_release_record")
        assert n >= 20, f"only {n} questions came from the release/CVE API"

    def test_more_than_one_endpoint_contributed(self, records):
        endpoints = {r["source_endpoint"] for r in records if r["source_endpoint"]}
        assert len(endpoints) >= 3, sorted(endpoints)


class TestHarnessIntegration:
    def test_load_dataset_returns_300(self):
        assert len(load_dataset(BENCHMARK_REL)) == EXPECTED_TOTAL

    def test_load_dataset_records_are_well_formed(self):
        for rec in load_dataset(BENCHMARK_REL):
            assert set(rec) == {"id", "query", "category", "ground_truth",
                                "reddit_id"}
            assert isinstance(rec["id"], int)
            assert isinstance(rec["query"], str) and rec["query"].strip()
            assert rec["category"] in EXPECTED_CATEGORIES

    def test_load_dataset_honours_limit(self):
        assert len(load_dataset(BENCHMARK_REL, limit=25)) == 25

    def test_load_dataset_preserves_ground_truth(self):
        recs = load_dataset(BENCHMARK_REL)
        assert sum(1 for r in recs if r["ground_truth"]) >= 20

    def test_no_network_needed(self, monkeypatch):
        """The benchmark must be usable with the APIs unreachable."""
        def blocked(*args, **kwargs):
            raise AssertionError("loading the benchmark must not use the network")

        monkeypatch.setattr(socket, "socket", blocked)
        monkeypatch.setattr(socket, "create_connection", blocked)
        assert len(load_dataset(BENCHMARK_REL)) == EXPECTED_TOTAL


class TestManifest:
    def test_manifest_agrees_with_the_dataset(self, records, manifest):
        assert manifest["total"] == len(records)
        for cat, n in manifest["categories"].items():
            assert sum(1 for r in records if r["category"] == cat) == n
        assert manifest["mined"] + manifest["backfilled"] == len(records)

    def test_manifest_records_endpoint_failures(self, manifest):
        assert isinstance(manifest["failed_requests"], list)

    def test_manifest_lists_backfilled_cells(self, records, manifest):
        cells = {(e, c) for e, c in map(tuple, manifest["backfilled_cells"])}
        actual = {(r["ecosystem"], r["category"]) for r in records
                  if r["source"] == "backfill_template"}
        assert cells == actual
