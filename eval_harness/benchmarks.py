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
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Sequence

from .config import ROOT

# Answers that decline rather than assert. Matched on word boundaries against
# the normalized prediction. Split by how much a marker can be trusted alone:
#
#   STRONG -- a refusal phrase that cannot plausibly sit inside a real answer.
#             Seeing one is enough to call the whole prediction an abstention.
#   WEAK   -- a bare word or short phrase that routinely appears *inside* a
#             correct answer ("the severity is unknown, but Firefox 149.0.1 is
#             the latest"). A weak marker may only downgrade a prediction that
#             has already failed the ground-truth match, never one that passed.
#
# Keep both lists conservative: a phrase here turns a would-be `incorrect` into
# a `missing`, which is scored more leniently.
STRONG_ABSTENTION_MARKERS = (
    "i don't know",
    "i do not know",
    "no relevant",
    "no matching source",
    "no matching vendor",
    "cannot determine",
    "can't determine",
    "unable to determine",
    "insufficient information",
    "insufficient evidence",
    "do not answer",
    "does not answer",
    "not enough information",
    "invalid question",
)

WEAK_ABSTENTION_MARKERS = (
    "unknown",
    "not found",
    "no information",
)

# Back-compat: callers that imported the flat tuple still work.
ABSTENTION_MARKERS = STRONG_ABSTENTION_MARKERS + WEAK_ABSTENTION_MARKERS

# Words that carry no discriminative weight when comparing a full-sentence gold
# answer against a paraphrase of it. "published"/"shipped"/"released" are the
# exact axis paraphrase varies along, so they must not count toward overlap;
# the version, the date, the vendor and the channel *name* are what decide
# whether an answer is right.
_CONTENT_STOPWORDS = frozenset("""
a an the this that these those it its is are was were be been being am
on in at of for to from by with and or but as so then than there here
new latest current recent stable available out now up
release releases released releasing publish published publishes shipped ships
ship update updates updated version versions channel channels build builds
was_published were_published has have had does do did will would can could
""".split())

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
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")


def extract_dates(text: str) -> List[str]:
    """Return ISO (YYYY-MM-DD) dates found in `text`.

    Dates are the second decisive fact in this domain (the first is the version
    number), and they survive normalization badly -- `normalize_answer` strips
    the hyphens, turning "2026-06-26" into the bare token "20260626". Pulling
    them out of the *raw* text keeps them comparable.
    """
    if not text:
        return []
    return ["-".join(m.groups()) for m in _ISO_DATE_RE.finditer(str(text))]


def date_surface_forms(iso: str) -> List[str]:
    """Normalized spellings a system might plausibly use for one ISO date.

    A prediction that says "June 26, 2026" is stating the same fact as a gold
    answer that says "2026-06-26"; scoring it wrong would punish formatting.
    """
    try:
        y, m, d = iso.split("-")
        month = _MONTHS[int(m) - 1]
    except (ValueError, IndexError):
        return [normalize_answer(iso)]
    day = str(int(d))
    forms = [
        f"{y}{m}{d}",                 # what normalize_answer() makes of the ISO form
        f"{y} {m} {d}",
        f"{month} {day} {y}",
        f"{month[:3]} {day} {y}",
        f"{day} {month} {y}",
        f"{day} {month[:3]} {y}",
    ]
    return [normalize_answer(f) for f in forms]


def extract_versions(text: str, multipart_only: bool = False) -> List[str]:
    """Return version-like tokens, normalized to dot form ('7_0_0' -> '7.0.0').

    Version agreement is the decisive signal for this domain: a software update
    answer is right or wrong largely on whether the version number matches.
    """
    if not text:
        return []
    out = []
    for m in _VERSION_RE.finditer(str(text)):
        v = m.group(1).replace("_", ".")
        if multipart_only and "." not in v:
            # A bare integer is not a version -- it is the year in a date, a
            # day number, a CVE count. Only dotted forms are decisive.
            continue
        out.append(v)
    return out


def _marker_present(norm_pred: str, marker: str) -> bool:
    """Word-boundary test for one marker against an already-normalized string."""
    m = normalize_answer(marker)
    if not m:
        return False
    return re.search(r"(?<!\w)" + re.escape(m) + r"(?!\w)", norm_pred) is not None


def is_abstention(prediction: str, strong_only: bool = False) -> bool:
    """True when the prediction declines to answer.

    Matching is on word boundaries, not raw substrings, so "unknowns" and
    "well-known" no longer trip the "unknown" marker. Pass `strong_only` to
    require an unambiguous refusal phrase; weak markers such as a bare
    "unknown" are common *inside* correct answers and are only meaningful once
    the prediction has already failed the ground-truth match.
    """
    norm = normalize_answer(prediction)
    if not norm:
        return False
    markers = (STRONG_ABSTENTION_MARKERS if strong_only
               else STRONG_ABSTENTION_MARKERS + WEAK_ABSTENTION_MARKERS)
    return any(_marker_present(norm, m) for m in markers)


# ------------------------------------------------------------------ matching

def content_tokens(text: str) -> List[str]:
    """Normalized tokens with filler removed, versions canonicalized.

    A leading "v" is stripped from version-like tokens so that "v7.0.0" and
    "7.0.0" -- which `normalize_answer` renders as "v700" and "700" -- agree.
    """
    out = []
    for tok in normalize_answer(text).split():
        if len(tok) > 1 and tok[0] == "v" and tok[1:].isdigit():
            tok = tok[1:]
        if tok in _CONTENT_STOPWORDS:
            continue
        out.append(tok)
    return out


def _dates_satisfied(gold_dates: Sequence[str], pred_norm: str) -> bool:
    """Every date asserted by the gold answer must appear in the prediction,
    in any of its common spellings."""
    for iso in gold_dates:
        if not any(_marker_present(pred_norm, form)
                   for form in date_surface_forms(iso)):
            return False
    return True


def _key_facts_match(gold: str, pred: str, pred_norm: str,
                     require_version_match: bool, min_recall: float) -> bool:
    """Fuzzy match for full-sentence gold answers.

    Requiring the whole gold string to appear verbatim in the prediction scores
    every paraphrase as a hallucination -- gold "Ubuntu 26.102.0 was published
    on 2026-06-26 on the minor channel" against prediction "Ubuntu 26.102.0
    shipped on 2026-06-26 on the minor release channel" is the same fact stated
    two ways. So instead:

      * every dotted version in the gold must appear in the prediction,
      * every date in the gold must appear in the prediction, and
      * the prediction must cover at least `min_recall` of the gold's remaining
        content tokens.

    The hard requirements are what keep this from being lenient: a prediction
    with the wrong version or the wrong date fails outright no matter how much
    surrounding wording it echoes.
    """
    gold_versions = set(extract_versions(gold, multipart_only=True))
    if require_version_match and gold_versions:
        pred_versions = set(extract_versions(pred, multipart_only=True))
        if not gold_versions.issubset(pred_versions):
            return False

    gold_dates = extract_dates(gold)
    if gold_dates and not _dates_satisfied(gold_dates, pred_norm):
        return False

    gold_toks = content_tokens(gold)
    if not gold_toks:
        # Nothing but filler and facts; the checks above already decided it.
        return bool(gold_versions or gold_dates)
    pred_toks = set(content_tokens(pred))
    hits = sum(1 for t in gold_toks if t in pred_toks)
    return (hits / len(gold_toks)) >= min_recall


# ------------------------------------------------------------------ scoring

def score_prediction(prediction: str,
                     ground_truth,
                     require_version_match: bool = True,
                     min_recall: float = 0.7) -> str:
    """Label one prediction as 'correct' | 'incorrect' | 'missing'.

    `ground_truth` may be a string or a list of acceptable strings.

    A prediction is `correct` when a normalized ground-truth string appears
    verbatim in the normalized prediction, or when it reproduces the gold
    answer's key facts -- see `_key_facts_match`. When both sides carry version
    numbers and `require_version_match` is set, the versions must agree as well
    -- this stops "Firefox 148" from being scored correct against a gold answer
    of "Firefox 149" merely because the product name matched.

    The abstention check runs *after* the gold match, not before: "the severity
    is unknown, but Firefox 149.0.1 is the latest" is a correct answer that
    happens to contain a hedge, and scoring it `missing` silently deflates
    accuracy. Only an unambiguous refusal short-circuits the match.
    """
    if ground_truth is None or (isinstance(ground_truth, str) and not ground_truth.strip()):
        return "missing"
    if prediction is None or not str(prediction).strip():
        return "missing"
    if is_abstention(prediction, strong_only=True):
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
        if _key_facts_match(str(gold), str(prediction), pred_n,
                            require_version_match, min_recall):
            return "correct"

    # No gold matched. A hedge word now decides between an honest decline and a
    # confident wrong answer.
    if is_abstention(prediction):
        return "missing"
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


def stratified_limit(records: Sequence[dict], limit: int,
                     key: str = "category") -> List[dict]:
    """Take `limit` records while preserving the balance of `key`.

    A plain head slice destroys the stratification the benchmark was built for.
    data/benchmark_300.json is written as five contiguous 60-question blocks in
    the order releases, bugs, security, community, general, so `--limit 100`
    yields 60 releases + 40 bugs and *zero* security, community or general
    questions -- two of five categories, reported as if it were the benchmark.

    This walks the groups round-robin in first-appearance order, taking each
    group's records in file order. That is deterministic (no RNG, no seed to
    thread through), it keeps within-group ordering so a `--resume` of a
    smaller limit stays a prefix, and it degrades gracefully when groups are
    uneven: a group that runs out simply stops contributing.

    Several comma-separated fields ("category,ecosystem") balance both
    dimensions, because balancing category alone still collapses ecosystem
    coverage -- each category block is itself ordered by ecosystem.

    The nesting matters, and flattening it is a trap. Grouping on the *tuple*
    ("releases", "Apple iOS") makes ~120 groups for benchmark_300, and a
    round-robin over 120 groups with `limit=30` never reaches the later
    categories: measured on the real file, tuple-grouping takes ecosystem
    coverage from 3 to 24 but drops category coverage from 5 to 2. It moves the
    collapse rather than removing it. So the walk is hierarchical instead: one
    step per top-level group per cycle, and each top-level group advances its
    own nested round-robin. Both dimensions stay balanced at any limit.
    """
    if not limit or limit <= 0 or limit >= len(records):
        return list(records)

    fields = [f.strip() for f in str(key).split(",") if f.strip()] or ["category"]

    def _nest(rows: Sequence[dict], depth: int):
        """Nested round-robin queues: a list of rows, or a list of sub-queues."""
        if depth >= len(fields):
            return list(rows)
        groups: "OrderedDict[object, List[dict]]" = OrderedDict()
        for r in rows:
            groups.setdefault(r.get(fields[depth]), []).append(r)
        return [_nest(g, depth + 1) for g in groups.values()]

    def _take(node) -> Optional[dict]:
        """Pop one record, advancing this node's round-robin by one position."""
        if not node:
            return None
        if isinstance(node[0], dict):          # leaf: a queue of records
            return node.pop(0)
        for i, child in enumerate(node):       # branch: try each sub-queue once
            got = _take(child)
            if got is not None:
                # Rotate so the next visit starts after the child just served.
                node.append(node.pop(i))
                return got
        return None

    tree = _nest(records, 0)
    out: List[dict] = []
    while len(out) < limit:
        progressed = False
        for top in list(tree):
            got = _take(top)
            if got is None:
                continue
            out.append(got)
            progressed = True
            if len(out) >= limit:
                break
        if not progressed:
            break
    return out


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
