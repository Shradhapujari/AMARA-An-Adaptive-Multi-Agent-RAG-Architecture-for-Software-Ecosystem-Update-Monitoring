"""
Established-benchmark support.
=============================
The reviewers' first ask was to score answers on an *established* benchmark
rather than only on our own Evaluator heuristic. This module supplies two
things the rest of the harness was missing:

  1. Loaders that normalize public benchmark files into the record shape
     `dataset.load_dataset` already produces, so `run_eval` can consume a
     benchmark with `--dataset <file> --benchmark crag`.

  2. CRAG-style scoring (Yang et al., "CRAG -- Comprehensive RAG Benchmark").
     Every prediction is labelled `correct`, `incorrect`, or `missing`, and
     the summary reports

         accuracy      = correct / n
         hallucination = incorrect / n
         missing       = missing / n
         crag_score    = accuracy - hallucination        in [-1, 1]

     The `crag_score` is the part that matters for this project: it *penalizes*
     a confident wrong answer and merely declines to reward an abstention, so a
     system that says "the sources do not answer this" scores strictly better
     than one that guesses. That is the property our Evaluator's own quality
     score cannot express.

Scoring here is string-based and deterministic — no LLM judge — so it is
reproducible and independent of the model under test. `judge.score_answer`
remains available for graded semantic scoring; the two are complementary.

Usage:
    from eval_harness.benchmarks import load_benchmark, score_prediction, summarize
    records = load_benchmark("crag_questions.jsonl", fmt="crag", limit=200)
    label   = score_prediction(pred_answer, rec["ground_truth"])
    stats   = summarize([...labels...])
"""

from __future__ import annotations

import json
import os
import re
import string
from typing import Dict, Iterable, List, Optional, Sequence

from .config import ROOT

# Answers that decline rather than assert. Matched case-insensitively against
# the normalized prediction. Keep this list conservative: a phrase here turns
# a would-be `incorrect` into a `missing`, which is scored more leniently.
ABSTENTION_MARKERS = (
    "i don't know",
    "i do not know",
    "unknown",
    "no relevant",
    "not found",
    "no matching source",
    "no matching vendor",
    "cannot determine",
    "can't determine",
    "unable to determine",
    "insufficient information",
    "insufficient evidence",
    "no information",
    "do not answer",
    "does not answer",
    "not enough information",
    "invalid question",
)

_ARTICLES = {"a", "an", "the"}
_PUNCT = str.maketrans("", "", string.punctuation)


# ---------------------------------------------------------------- normalize

def normalize_answer(text: str) -> str:
    """Lowercase, strip punctuation/articles/extra whitespace.

    Follows the usual SQuAD-style normalization so that "Firefox v149.0.1" and
    "firefox 149.0.1" compare equal.
    """
    if text is None:
        return ""
    s = str(text).lower().strip()
    s = s.replace("—", " ").replace("–", " ")
    s = s.translate(_PUNCT)
    tokens = [t for t in s.split() if t not in _ARTICLES]
    return " ".join(tokens)


_VERSION_RE = re.compile(r"\bv?(\d+(?:[._]\d+){0,3})\b")


def extract_versions(text: str) -> List[str]:
    """Return version-like tokens, normalized to dot form ('7_0_0' -> '7.0.0').

    Version agreement is the decisive signal for this domain: a software update
    answer is right or wrong largely on whether the version number matches.
    """
    if not text:
        return []
    out = []
    for m in _VERSION_RE.finditer(str(text)):
        out.append(m.group(1).replace("_", "."))
    return out


def is_abstention(prediction: str) -> bool:
    norm = " " + normalize_answer(prediction) + " "
    return any(normalize_answer(m) in norm for m in ABSTENTION_MARKERS)


# ------------------------------------------------------------------ scoring

def score_prediction(prediction: str,
                     ground_truth,
                     require_version_match: bool = True) -> str:
    """Label one prediction as 'correct' | 'incorrect' | 'missing'.

    `ground_truth` may be a string or a list of acceptable strings.

    A prediction is `correct` when a normalized ground-truth string appears in
    the normalized prediction. When both sides carry version numbers and
    `require_version_match` is set, the versions must agree as well — this
    stops "Firefox 148" from being scored correct against a gold answer of
    "Firefox 149" merely because the product name matched.
    """
    if ground_truth is None or (isinstance(ground_truth, str) and not ground_truth.strip()):
        return "missing"
    if prediction is None or not str(prediction).strip():
        return "missing"
    if is_abstention(prediction):
        return "missing"

    golds = ground_truth if isinstance(ground_truth, (list, tuple)) else [ground_truth]
    pred_n = normalize_answer(prediction)
    pred_versions = set(extract_versions(prediction))

    for gold in golds:
        gold_n = normalize_answer(gold)
        if not gold_n:
            continue
        if gold_n in pred_n or pred_n == gold_n:
            gold_versions = set(extract_versions(gold))
            if require_version_match and gold_versions:
                if not (gold_versions & pred_versions):
                    continue
            return "correct"
    return "incorrect"


def summarize(labels: Sequence[str]) -> Dict[str, float]:
    """Aggregate labels into CRAG-style rates plus the composite score."""
    n = len(labels)
    if n == 0:
        return {"n": 0, "accuracy": 0.0, "hallucination": 0.0,
                "missing": 0.0, "crag_score": 0.0}
    correct = sum(1 for x in labels if x == "correct")
    incorrect = sum(1 for x in labels if x == "incorrect")
    missing = sum(1 for x in labels if x == "missing")
    acc = correct / n
    hall = incorrect / n
    return {
        "n": n,
        "correct": correct,
        "incorrect": incorrect,
        "missing_n": missing,
        "accuracy": round(acc, 4),
        "hallucination": round(hall, 4),
        "missing": round(missing / n, 4),
        "crag_score": round(acc - hall, 4),
    }


# ------------------------------------------------------------------ loaders

def _read_any(path: str) -> List[dict]:
    """Read .json (list or wrapped list) or .jsonl into a list of dicts."""
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(full):
        raise FileNotFoundError(
            f"benchmark file not found: {full}\n"
            "Download the benchmark and point --dataset at it."
        )
    rows: List[dict] = []
    if full.endswith(".jsonl"):
        with open(full, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    with open(full, "r") as f:
        data = json.load(f)
    if isinstance(data, dict):
        for key in ("questions", "data", "items", "examples"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError(f"{path}: could not find a question list in dict")
    return data


def _norm_crag(raw: dict, idx: int) -> Optional[dict]:
    query = raw.get("query") or raw.get("question")
    if not query:
        return None
    gold = raw.get("answer")
    if gold is None:
        gold = raw.get("ground_truth") or raw.get("gold_answer") or raw.get("gt")
    return {
        "id": raw.get("interaction_id") or raw.get("id", idx),
        "query": str(query).strip(),
        "category": raw.get("question_type") or raw.get("domain") or "general",
        "ground_truth": gold,
        "reddit_id": None,
        "benchmark": "crag",
        "dynamism": raw.get("static_or_dynamic"),
    }


def _norm_generic(raw: dict, idx: int) -> Optional[dict]:
    query = raw.get("query") or raw.get("question") or raw.get("title")
    if not query:
        return None
    gold = (raw.get("ground_truth") or raw.get("answer")
            or raw.get("gold_answer") or raw.get("gt"))
    return {
        "id": raw.get("id", idx),
        "query": str(query).strip(),
        "category": raw.get("category", raw.get("sub", "general")),
        "ground_truth": gold,
        "reddit_id": raw.get("reddit_id") or raw.get("url"),
        "benchmark": "generic",
        "dynamism": None,
    }


_LOADERS = {"crag": _norm_crag, "generic": _norm_generic}


def load_benchmark(path: str, fmt: str = "crag", limit: int = 0,
                   require_ground_truth: bool = True) -> List[dict]:
    """Load a benchmark file into harness record shape.

    `require_ground_truth` drops questions with no gold answer — scoring them
    would silently inflate the `missing` rate for every system.
    """
    fmt = (fmt or "generic").lower()
    if fmt not in _LOADERS:
        raise ValueError(f"unknown benchmark format {fmt!r}; expected one of {sorted(_LOADERS)}")
    norm = _LOADERS[fmt]
    rows = _read_any(path)
    records: List[dict] = []
    dropped = 0
    for i, raw in enumerate(rows, 1):
        if isinstance(raw, str):
            raw = {"query": raw}
        rec = norm(raw, i)
        if not rec:
            continue
        if require_ground_truth and not rec.get("ground_truth"):
            dropped += 1
            continue
        records.append(rec)
    if dropped:
        print(f"[benchmarks] dropped {dropped} question(s) with no ground truth")
    if limit and limit > 0:
        records = records[:limit]
    return records


def score_run(per_query: Iterable[dict],
              records_by_id: Dict[object, dict]) -> Dict[str, Dict[str, float]]:
    """Score an entire run's per_query rows, grouped by system.

    Returns {system_name: summary_dict}. Rows whose question has no ground
    truth are skipped rather than counted as missing.
    """
    by_system: Dict[str, List[str]] = {}
    for row in per_query:
        rec = records_by_id.get(row.get("query_id"))
        if not rec or not rec.get("ground_truth"):
            continue
        label = score_prediction(row.get("answer", ""), rec["ground_truth"])
        by_system.setdefault(row["system"], []).append(label)
    return {sys_name: summarize(labels) for sys_name, labels in by_system.items()}
