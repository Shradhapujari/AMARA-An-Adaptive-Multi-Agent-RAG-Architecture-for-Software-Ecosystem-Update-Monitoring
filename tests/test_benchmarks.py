"""Offline tests for benchmark loading and CRAG-style scoring."""
import json
import os
import tempfile

import pytest

from eval_harness import benchmarks as B


class TestNormalize:
    def test_case_and_punctuation(self):
        assert B.normalize_answer("The Answer.") == "answer"
        assert B.normalize_answer("  Firefox   Released!  ") == "firefox released"

    def test_none_is_empty(self):
        assert B.normalize_answer(None) == ""


class TestVersions:
    def test_extracts_dotted(self):
        assert "149.0.1" in B.extract_versions("Firefox v149.0.1 shipped")

    def test_normalizes_underscores(self):
        assert "7.0.0" in B.extract_versions("linux v7_0_0")

    def test_empty(self):
        assert B.extract_versions("") == []


class TestAbstention:
    @pytest.mark.parametrize("text", [
        "I don't know based on the retrieved sources.",
        "No matching source was found.",
        "The retrieved documents contain insufficient information.",
        "Unable to determine the version.",
    ])
    def test_detects(self, text):
        assert B.is_abstention(text)

    def test_normal_answer_is_not_abstention(self):
        assert not B.is_abstention("Firefox 149.0.1 was released on April 7 2026.")


class TestScorePrediction:
    def test_correct_substring(self):
        assert B.score_prediction("The latest is Firefox 149.0.1.",
                                  "Firefox 149.0.1") == "correct"

    def test_wrong_version_is_incorrect(self):
        # Product name matches but the version does not -- must not score correct.
        assert B.score_prediction("The latest is Firefox 148.0.1.",
                                  "Firefox 149.0.1") == "incorrect"

    def test_abstention_is_missing_not_incorrect(self):
        assert B.score_prediction("I don't know.", "Firefox 149.0.1") == "missing"

    def test_empty_prediction_is_missing(self):
        assert B.score_prediction("", "Firefox 149.0.1") == "missing"

    def test_accepts_list_of_golds(self):
        assert B.score_prediction("It is v7.0.0.",
                                  ["linux 7.0.0", "v7.0.0"]) == "correct"

    def test_no_ground_truth_is_missing(self):
        assert B.score_prediction("anything", None) == "missing"

    def test_version_check_can_be_disabled(self):
        assert B.score_prediction("Firefox 148", "Firefox",
                                  require_version_match=False) == "correct"


class TestSummarize:
    def test_rates_and_score(self):
        s = B.summarize(["correct"] * 6 + ["incorrect"] * 2 + ["missing"] * 2)
        assert s["n"] == 10
        assert s["accuracy"] == 0.6
        assert s["hallucination"] == 0.2
        assert s["missing"] == 0.2
        assert s["crag_score"] == pytest.approx(0.4)

    def test_abstaining_beats_guessing(self):
        """The property that motivates CRAG scoring: declining is better than
        answering wrongly."""
        guesser = B.summarize(["correct"] * 5 + ["incorrect"] * 5)
        abstainer = B.summarize(["correct"] * 5 + ["missing"] * 5)
        assert abstainer["crag_score"] > guesser["crag_score"]

    def test_empty(self):
        assert B.summarize([])["n"] == 0


class TestLoadBenchmark:
    def _write(self, rows, suffix=".jsonl"):
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w") as f:
            if suffix == ".jsonl":
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            else:
                json.dump(rows, f)
        return path

    def test_loads_crag_jsonl(self):
        path = self._write([
            {"interaction_id": "a1", "query": "latest firefox?",
             "answer": "149.0.1", "question_type": "simple",
             "static_or_dynamic": "dynamic"},
        ])
        recs = B.load_benchmark(path, fmt="crag")
        assert len(recs) == 1
        assert recs[0]["id"] == "a1"
        assert recs[0]["ground_truth"] == "149.0.1"
        assert recs[0]["category"] == "simple"
        os.unlink(path)

    def test_drops_rows_without_ground_truth(self):
        path = self._write([
            {"query": "has gold", "answer": "x"},
            {"query": "no gold"},
        ])
        recs = B.load_benchmark(path, fmt="crag")
        assert len(recs) == 1
        os.unlink(path)

    def test_limit(self):
        path = self._write([{"query": f"q{i}", "answer": "a"} for i in range(10)])
        assert len(B.load_benchmark(path, fmt="crag", limit=3)) == 3
        os.unlink(path)

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            B.load_benchmark("nope.json", fmt="bogus")

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            B.load_benchmark("definitely_not_here_12345.jsonl", fmt="crag")


class TestScoreRun:
    def test_groups_by_system(self):
        records = {1: {"id": 1, "ground_truth": "Firefox 149.0.1"}}
        per_query = [
            {"query_id": 1, "system": "marag", "answer": "It is Firefox 149.0.1"},
            {"query_id": 1, "system": "single_agent", "answer": "It is Firefox 148.0.1"},
        ]
        out = B.score_run(per_query, records)
        assert out["marag"]["accuracy"] == 1.0
        assert out["single_agent"]["hallucination"] == 1.0


class TestParaphraseScoring:
    """Full-sentence gold answers must survive being restated.

    The generator emits sentence-shaped golds ("X was published on <date> on
    the <channel> channel"), and requiring that whole string to appear verbatim
    in the prediction scored every paraphrase as a hallucination -- driving
    hallucination to ~1.0 and crag_score to ~-1.0 for every system.
    """

    GOLD = "Ubuntu 26.102.0 was published on 2026-06-26 on the minor channel."

    def test_paraphrase_is_correct(self):
        pred = "Ubuntu 26.102.0 shipped on 2026-06-26 on the minor release channel."
        assert B.score_prediction(pred, self.GOLD) == "correct"

    def test_alternate_date_spelling_is_correct(self):
        pred = "Ubuntu 26.102.0 shipped on June 26, 2026 on the minor channel."
        assert B.score_prediction(pred, self.GOLD) == "correct"

    def test_wrong_version_still_incorrect(self):
        pred = "Ubuntu 26.101.0 shipped on 2026-06-26 on the minor channel."
        assert B.score_prediction(pred, self.GOLD) == "incorrect"

    def test_wrong_date_still_incorrect(self):
        pred = "Ubuntu 26.102.0 shipped on 2026-07-26 on the minor channel."
        assert B.score_prediction(pred, self.GOLD) == "incorrect"

    def test_unrelated_answer_still_incorrect(self):
        assert B.score_prediction("Chrome is a browser made by Google.",
                                  self.GOLD) == "incorrect"


class TestAbstentionOrdering:
    """A hedge word inside a correct answer must not cost accuracy."""

    def test_hedge_in_correct_answer_scores_correct(self):
        pred = "The severity is unknown, but Firefox 149.0.1 is the latest."
        assert B.score_prediction(pred, "Firefox 149.0.1") == "correct"

    def test_hedge_alone_still_missing(self):
        assert B.score_prediction("The severity is unknown.",
                                  "Firefox 149.0.1") == "missing"

    def test_weak_marker_needs_word_boundary(self):
        assert not B.is_abstention("Unknowns aside, Firefox 149.0.1 shipped.")

    def test_strong_marker_short_circuits(self):
        assert B.is_abstention("I don't know.", strong_only=True)
        assert not B.is_abstention("The severity is unknown.", strong_only=True)


class TestStratifiedLimit:
    """`--limit N` must not silently drop whole categories.

    data/benchmark_300.json is five contiguous 60-question blocks in the order
    releases, bugs, security, community, general, so a head slice of 100 yields
    60 releases + 40 bugs and nothing else.
    """

    def _blocked(self):
        rows = []
        for cat, n in (("releases", 6), ("bugs", 6), ("security", 6)):
            rows += [{"id": f"{cat}{i}", "category": cat} for i in range(n)]
        return rows

    def test_head_slice_loses_categories(self):
        rows = self._blocked()
        head = rows[:6]
        assert {r["category"] for r in head} == {"releases"}

    def test_stratified_keeps_every_category(self):
        rows = self._blocked()
        out = B.stratified_limit(rows, 6, "category")
        assert len(out) == 6
        assert {r["category"] for r in out} == {"releases", "bugs", "security"}

    def test_balance_is_even_when_divisible(self):
        out = B.stratified_limit(self._blocked(), 9, "category")
        counts = {}
        for r in out:
            counts[r["category"]] = counts.get(r["category"], 0) + 1
        assert counts == {"releases": 3, "bugs": 3, "security": 3}

    def test_is_deterministic(self):
        rows = self._blocked()
        assert ([r["id"] for r in B.stratified_limit(rows, 7, "category")]
                == [r["id"] for r in B.stratified_limit(rows, 7, "category")])

    def test_smaller_limit_is_a_prefix_of_larger(self):
        """So resuming a run at a bigger limit reuses the earlier questions."""
        rows = self._blocked()
        small = [r["id"] for r in B.stratified_limit(rows, 6, "category")]
        big = [r["id"] for r in B.stratified_limit(rows, 12, "category")]
        assert big[:6] == small

    def test_limit_at_or_above_size_returns_all(self):
        rows = self._blocked()
        assert len(B.stratified_limit(rows, len(rows), "category")) == len(rows)
        assert len(B.stratified_limit(rows, 999, "category")) == len(rows)
        assert len(B.stratified_limit(rows, 0, "category")) == len(rows)

    def test_uneven_groups_degrade_gracefully(self):
        rows = ([{"id": f"a{i}", "category": "a"} for i in range(5)]
                + [{"id": "b0", "category": "b"}])
        out = B.stratified_limit(rows, 4, "category")
        assert len(out) == 4
        assert sum(1 for r in out if r["category"] == "b") == 1

    def test_real_benchmark_first_100_vs_stratified(self):
        import json, os
        from eval_harness.config import ROOT
        path = os.path.join(ROOT, "data", "benchmark_300.json")
        if not os.path.exists(path):
            pytest.skip("benchmark_300.json not present")
        rows = json.load(open(path))
        head_cats = {r["category"] for r in rows[:100]}
        strat = B.stratified_limit(rows, 100, "category")
        strat_cats = {r["category"] for r in strat}
        assert len(head_cats) == 2, f"expected head slice to lose categories, got {head_cats}"
        assert len(strat_cats) == 5, f"stratified should keep all 5, got {strat_cats}"
        assert len(strat) == 100


class TestStratifiedLimitCompositeKey:
    """Balancing one field is not enough when the blocks nest.

    Each category block in benchmark_300.json is itself ordered by ecosystem,
    so `--stratify category` takes the first 20 of each 60-block and sees only
    ~10 of 24 ecosystems. A composite key balances the cross product.
    """

    def _nested(self):
        rows = []
        for cat in ("releases", "bugs"):
            for eco in ("ubuntu", "chrome", "docker", "npm"):
                rows += [{"id": f"{cat}-{eco}-{i}", "category": cat,
                          "ecosystem": eco} for i in range(3)]
        return rows

    def test_single_key_collapses_the_nested_field(self):
        out = B.stratified_limit(self._nested(), 4, "category")
        assert len({r["category"] for r in out}) == 2
        assert len({r["ecosystem"] for r in out}) < 4

    def test_composite_key_covers_both(self):
        out = B.stratified_limit(self._nested(), 8, "category,ecosystem")
        assert len(out) == 8
        assert len({r["category"] for r in out}) == 2
        assert len({r["ecosystem"] for r in out}) == 4

    def test_whitespace_and_single_field_still_work(self):
        rows = self._nested()
        a = B.stratified_limit(rows, 6, "category")
        b = B.stratified_limit(rows, 6, " category ")
        assert [r["id"] for r in a] == [r["id"] for r in b]

    def test_composite_is_deterministic(self):
        rows = self._nested()
        assert ([r["id"] for r in B.stratified_limit(rows, 7, "category,ecosystem")]
                == [r["id"] for r in B.stratified_limit(rows, 7, "category,ecosystem")])
