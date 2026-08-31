#!/usr/bin/env python3
"""
Merge an arm measured in one run into another run's artifacts.
==============================================================
`--resume <run_dir> --generators <arm>` is the supported way to add an arm to a
finished run. This exists for the case where that did not happen and the arm
landed in its own directory -- and it refuses the merge unless the two runs are
actually comparable, because an arm measured under different conditions is not
a column in someone else's table.

Checked before anything is written:

  same dataset      both run ids carry the same dataset hash
  same questions    the arm covers exactly the question ids of the target
  same judge        config.json judge specs agree
  same corpus       config.json corpus mode agrees (a live-corpus arm cannot be
                    compared against a frozen-corpus one: the documents move)
  same retrieval    optional but recommended: --expect-same-retrieval-as <arm>
                    asserts the merged arm returns the identical ranked doc_ids
                    as an arm already in the target. That is what licenses
                    reading a difference between them as an answer-side effect,
                    and it is also the sharpest available check that the two
                    runs really did see the same corpus.

The target's per_query.jsonl is backed up before it is touched.

Usage:
    python merge_arm.py results/run_TARGET results/run_SOURCE --arm marag_llm \
        --expect-same-retrieval-as marag
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from typing import Dict, List


def _rows(run_dir: str) -> List[dict]:
    with open(os.path.join(run_dir, "per_query.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def _cfg(run_dir: str) -> dict:
    p = os.path.join(run_dir, "config.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def _dataset_hash(run_dir: str) -> str:
    return os.path.basename(run_dir.rstrip(os.sep)).rsplit("_", 1)[-1]


def _corpus_mode(cfg: dict) -> object:
    c = cfg.get("corpus")
    return c.get("mode") if isinstance(c, dict) else c


def check(target: str, source: str, arm: str, expect_same_as: str = "") -> List[str]:
    """Return a list of reasons the merge must not happen. Empty means go."""
    problems: List[str] = []

    if _dataset_hash(target) != _dataset_hash(source):
        problems.append(
            f"different datasets: target hash {_dataset_hash(target)} vs "
            f"source hash {_dataset_hash(source)}")

    tcfg, scfg = _cfg(target), _cfg(source)
    if tcfg.get("judge") and scfg.get("judge") and tcfg["judge"] != scfg["judge"]:
        problems.append(f"different judges: {tcfg['judge']} vs {scfg['judge']}")
    if _corpus_mode(tcfg) != _corpus_mode(scfg):
        problems.append(
            f"different corpus mode: {_corpus_mode(tcfg)} vs {_corpus_mode(scfg)} "
            f"— the documents are not the same, so the arms are not comparable")

    trows, srows = _rows(target), _rows(source)
    arm_rows = [r for r in srows if r["system"] == arm]
    if not arm_rows:
        problems.append(f"source has no rows for arm {arm!r}")
        return problems

    if arm in {r["system"] for r in trows}:
        problems.append(f"target already has arm {arm!r}")

    t_qids = {r["query_id"] for r in trows}
    a_qids = {r["query_id"] for r in arm_rows}
    if a_qids != t_qids:
        problems.append(
            f"question sets differ: target has {len(t_qids)}, arm covers "
            f"{len(a_qids)}, {len(t_qids - a_qids)} missing from the arm")

    if expect_same_as:
        ref = {r["query_id"]: r["doc_ids"] for r in trows
               if r["system"] == expect_same_as}
        if not ref:
            problems.append(f"target has no arm {expect_same_as!r} to compare "
                            f"retrieval against")
        else:
            mismatched = [r["query_id"] for r in arm_rows
                          if r["query_id"] in ref
                          and r["doc_ids"] != ref[r["query_id"]]]
            if mismatched:
                problems.append(
                    f"retrieval differs from {expect_same_as!r} on "
                    f"{len(mismatched)} question(s) (e.g. {mismatched[:5]}): "
                    f"the runs did not see the same corpus, so merging would "
                    f"hide a confound rather than remove one")
    return problems


def merge(target: str, source: str, arm: str, expect_same_as: str = "",
          force: bool = False) -> int:
    problems = check(target, source, arm, expect_same_as)
    if problems and not force:
        for p in problems:
            print(f"  REFUSED: {p}")
        raise SystemExit("merge refused; nothing was written")
    for p in problems:
        print(f"  WARNING (forced): {p}")

    path = os.path.join(target, "per_query.jsonl")
    shutil.copy2(path, path + ".before_merge")
    arm_rows = [r for r in _rows(source) if r["system"] == arm]
    # A file whose last line has no newline would otherwise swallow the first
    # merged row into it, and the result is not JSON on that line at all.
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
    with open(path, "a") as f:
        for r in arm_rows:
            f.write(json.dumps(r) + "\n")

    cfg = _cfg(target)
    if cfg:
        cfg.setdefault("systems_evaluated", [])
        if arm not in cfg["systems_evaluated"]:
            cfg["systems_evaluated"].append(arm)
        cfg.setdefault("merged_arms", []).append(
            {"arm": arm, "from": os.path.basename(source.rstrip(os.sep))})
        json.dump(cfg, open(os.path.join(target, "config.json"), "w"), indent=2)
    return len(arm_rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target")
    ap.add_argument("source")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--expect-same-retrieval-as", default="", metavar="ARM")
    ap.add_argument("--force", action="store_true",
                    help="merge despite failed checks; every reason is printed")
    ap.add_argument("--no-report", action="store_true")
    a = ap.parse_args()

    n = merge(a.target, a.source, a.arm, a.expect_same_retrieval_as, a.force)
    print(f"[merged] {n} rows for {a.arm} into {a.target}")

    if not a.no_report:
        from eval_harness import report as report_mod
        rows = _rows(a.target)
        cfg = _cfg(a.target)
        agg = report_mod.aggregate(rows, cfg.get("ks", [1, 3, 5]))
        report_mod.write_csv(agg, os.path.join(a.target, "aggregate.csv"))
        report_mod.write_markdown(agg, cfg, os.path.join(a.target, "report.md"))
        print(f"[regenerated] report.md and aggregate.csv")


if __name__ == "__main__":
    main()
