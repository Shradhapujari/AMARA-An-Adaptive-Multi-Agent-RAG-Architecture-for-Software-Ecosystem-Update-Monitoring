"""A run's own artifacts must reproduce the numbers that run reported.

This guards a defect found by re-deriving the metrics independently: `run_eval`
scored each query against the *per-query pool* of judged documents, but wrote
the accumulating cross-run judgment cache to `qrels.json`. Recomputing
`per_query.jsonl`'s `ir` block from that file reproduced 2 of 20 rows -- the
recall and nDCG denominators came from a much larger judged pool (1-3 relevant
docs per query in the pool vs 2-10 in the cache).

`qrels.json` is now `{query_id: {doc_id: grade}}` for the judgments that
actually scored the run. Old run directories carry the flat
`"<id>:<doc_id>"` cache shape and are skipped.
"""
from __future__ import annotations

import glob
import json
import os

import pytest

from eval_harness.config import ROOT
from eval_harness.metrics import retrieval_metrics

RESULTS = os.path.join(ROOT, "results")


def _new_format(qrels: dict) -> bool:
    """New shape: values are dicts of doc_id -> grade. Old shape: flat ints."""
    return bool(qrels) and all(isinstance(v, dict) for v in qrels.values())


def _run_dirs():
    if not os.path.isdir(RESULTS):
        return []
    out = []
    for d in sorted(glob.glob(os.path.join(RESULTS, "run_*"))):
        if (os.path.exists(os.path.join(d, "qrels.json"))
                and os.path.exists(os.path.join(d, "per_query.jsonl"))):
            out.append(d)
    return out


class TestQrelsProvenance:
    def test_new_runs_reproduce_their_own_metrics(self):
        checked = 0
        for d in _run_dirs():
            qrels = json.load(open(os.path.join(d, "qrels.json")))
            if not _new_format(qrels):
                continue          # pre-fix run directory
            rows = [json.loads(l) for l in
                    open(os.path.join(d, "per_query.jsonl"))]
            for r in rows:
                stored = r.get("ir") or {}
                if not stored:
                    continue
                per_q = qrels.get(str(r["query_id"]), {})
                ks = sorted({int(k.split("@")[1]) for k in stored if "@" in k})
                got = retrieval_metrics(r["doc_ids"], per_q, ks)
                for key, want in stored.items():
                    if key in got:
                        assert got[key] == pytest.approx(want, abs=1e-9), (
                            f"{os.path.basename(d)} q{r['query_id']} "
                            f"{r['system']} {key}: artifact gives {got[key]}, "
                            f"run reported {want}")
                        checked += 1
        if checked == 0:
            pytest.skip("no post-fix run directories present yet")

    def test_cache_snapshot_is_not_the_scoring_qrels(self):
        """Where both files exist, they must not be the same object -- that
        sameness was the bug."""
        for d in _run_dirs():
            snap = os.path.join(d, "qrels_cache_snapshot.json")
            if not os.path.exists(snap):
                continue
            qrels = json.load(open(os.path.join(d, "qrels.json")))
            assert _new_format(qrels), (
                f"{os.path.basename(d)}/qrels.json is still the flat cache shape")


class TestReproducibilityHarnessItself:
    def test_flat_cache_shape_is_rejected_as_scoring_qrels(self):
        """The detector must actually distinguish the two shapes, or the test
        above would pass vacuously on a regression."""
        assert not _new_format({"1:abc": 0, "1:def": 2})
        assert _new_format({"1": {"abc": 0, "def": 2}})
        assert not _new_format({})
