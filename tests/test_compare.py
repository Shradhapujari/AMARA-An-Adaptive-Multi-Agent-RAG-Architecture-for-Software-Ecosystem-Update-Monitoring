"""Tests for the paired head-to-head comparison statistics.

The t-test implementation is validated against known reference values so the
pure-Python version (no scipy dependency at runtime) stays trustworthy.
"""
import json
import math
import os
import tempfile

import pytest

from eval_harness import compare as C


class TestIncompleteBeta:
    def test_bounds(self):
        assert C.betainc(2.0, 3.0, 0.0) == 0.0
        assert C.betainc(2.0, 3.0, 1.0) == 1.0

    def test_symmetry(self):
        # I_x(a,a) = 1 - I_(1-x)(a,a)
        assert C.betainc(3.0, 3.0, 0.3) == pytest.approx(1 - C.betainc(3.0, 3.0, 0.7), abs=1e-9)


class TestPairedTTest:
    def test_matches_reference(self):
        """Reference computed with scipy.stats.ttest_rel."""
        a = [0.8, 0.7, 0.9, 0.6, 0.85]
        b = [0.6, 0.65, 0.7, 0.55, 0.6]
        r = C.paired_t_test(a, b)
        assert r["n"] == 5 and r["df"] == 4
        assert r["t"] == pytest.approx(3.585686, abs=1e-5)
        assert r["p"] == pytest.approx(0.02305037, abs=1e-7)

    def test_identical_inputs_give_p_one(self):
        a = [0.5, 0.6, 0.7]
        assert C.paired_t_test(a, list(a))["p"] == 1.0

    def test_single_pair_is_undefined(self):
        assert math.isnan(C.paired_t_test([0.5], [0.4])["t"])


class TestBootstrap:
    def test_ci_brackets_mean(self):
        a = [0.8] * 20
        b = [0.6] * 20
        r = C.paired_bootstrap(a, b, iters=500, seed=1)
        assert r["mean_diff"] == pytest.approx(0.2)
        assert r["ci_low"] == pytest.approx(0.2)
        assert r["ci_high"] == pytest.approx(0.2)

    def test_deterministic_under_seed(self):
        a = [0.1, 0.9, 0.4, 0.7, 0.2]
        b = [0.2, 0.3, 0.5, 0.4, 0.6]
        r1 = C.paired_bootstrap(a, b, iters=300, seed=7)
        r2 = C.paired_bootstrap(a, b, iters=300, seed=7)
        assert r1 == r2


class TestWinTieLoss:
    def test_counts(self):
        # diffs: +1, 0, -2, +3  ->  2 wins, 1 tie, 1 loss
        assert C.win_tie_loss([1, 2, 3, 4], [0, 2, 5, 1]) == (2, 1, 1)

    def test_all_ties(self):
        assert C.win_tie_loss([1, 1], [1, 1]) == (0, 2, 0)


class TestHolm:
    def test_step_down(self):
        assert [round(x, 4) for x in C.holm([0.01, 0.04, 0.03])] == [0.03, 0.06, 0.06]

    def test_monotone_non_decreasing(self):
        raw = [0.001, 0.002, 0.5]
        out = C.holm(raw)
        # Adjustment never decreases a p-value.
        assert all(o >= i for o, i in zip(out, raw))
        # Step-down keeps adjusted values non-decreasing in rank order.
        ordered = [out[i] for i in sorted(range(len(raw)), key=lambda i: raw[i])]
        assert ordered == sorted(ordered)

    def test_empty(self):
        assert C.holm([]) == []


class TestMatrixAndPairing:
    ROWS = [
        {"query_id": 1, "system": "marag", "ir": {"ndcg@5": 0.9}, "answer_scores": {}},
        {"query_id": 1, "system": "single_agent", "ir": {"ndcg@5": 0.5}, "answer_scores": {}},
        {"query_id": 2, "system": "marag", "ir": {"ndcg@5": 0.7}, "answer_scores": {}},
        {"query_id": 2, "system": "single_agent", "ir": {"ndcg@5": 0.8}, "answer_scores": {}},
        # marag-only question: must be excluded from the paired comparison
        {"query_id": 3, "system": "marag", "ir": {"ndcg@5": 1.0}, "answer_scores": {}},
    ]

    def test_pairs_only_shared_questions(self):
        m = C.build_matrix(self.ROWS, "ndcg@5")
        a, b = C.paired_vectors(m, "marag", "single_agent")
        assert len(a) == len(b) == 2

    def test_compare_metric_reports_diff(self):
        res = C.compare_metric(self.ROWS, "ndcg@5", "single_agent", bootstrap_iters=200)
        assert len(res) == 1
        r = res[0]
        assert r["system"] == "marag" and r["n"] == 2
        assert r["mean_diff"] == pytest.approx((0.4 + -0.1) / 2)
        assert "p_holm" in r

    def test_unknown_baseline_returns_empty(self):
        assert C.compare_metric(self.ROWS, "ndcg@5", "nope") == []


class TestLoadPerQuery:
    def test_reads_jsonl(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "per_query.jsonl"), "w") as f:
            f.write(json.dumps({"query_id": 1, "system": "x"}) + "\n")
        assert len(C.load_per_query(d)) == 1

    def test_missing_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            C.load_per_query(tempfile.mkdtemp())


class TestBootstrapPFloor:
    """A raw tail proportion of 0 claims more evidence than the resamples give."""

    def test_p_is_never_exactly_zero(self):
        from eval_harness.compare import paired_bootstrap
        out = paired_bootstrap([1.0] * 20, [0.0] * 20, iters=1000)
        assert out["p"] > 0.0
        # two-sided: 2 * (0 crossings + 1) / (iters + 1)
        assert out["p"] == pytest.approx(2.0 / 1001, rel=1e-6)

    def test_identical_vectors_give_p_one(self):
        from eval_harness.compare import paired_bootstrap
        out = paired_bootstrap([0.5, 0.4, 0.6], [0.5, 0.4, 0.6], iters=500)
        assert out["p"] == pytest.approx(1.0)
