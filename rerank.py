"""
Candidate reranking for the Retriever Agent.
============================================
Why this module exists
----------------------
`eval_harness/FINDINGS.md` documented a reproducible defect: on standard IR
metrics (nDCG/Recall/MRR over judged relevance) the multi-agent pipeline lost
to the single-agent baseline, and the Query Rewriter *hurt* 7 of 10 queries
while helping none.

The cause is in `RetrieverAgent.run`: the final ordering is a substring
"boost" computed from the first four tokens of the **rewritten** query. A
rewrite turns a short user question ("G6 Bullet unstable?") into verbose
document vocabulary ("Unstable behavior in G6 Bullet software: ..."), so the
tokens driving the boost become filler and the boost promotes the wrong
documents. Rewriting widens *recall* at the fetch step but destroys *precision*
at the ranking step.

The fix keeps both properties by separating them, which is the multi-agent
argument the paper wants to make:

    rewritten query  ->  used to FETCH   (recall: vendor terms, synonyms)
    original query   ->  used to RANK    (precision: what the user asked)

A reranker scores the fetched candidate pool against the user's original
question and returns the top-k. Three backends are provided so the choice is
an experiment rather than an assumption:

    none      reproduce the published behaviour (first-4-token substring boost)
    bm25      Okapi BM25 over the pool, pure Python, deterministic, no model
    embed     cosine similarity over Ollama embeddings (semantic matching)

`none` is kept deliberately: it is the ablation arm that reproduces the
paper's original numbers.

Selection is by spec string, so it can be driven from an environment variable
and swept in an ablation without editing agent code:

    MARAG_RERANK=none            MARAG_RERANK=bm25
    MARAG_RERANK=embed           MARAG_RERANK=embed:nomic-embed-text

`embed` degrades to `bm25` when Ollama has no embedding model available, and
reports that it did so via `Reranker.degraded`, so a run never silently
measures something other than what it claims to measure.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Sequence

DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_SPEC = os.environ.get("MARAG_RERANK", "embed")

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")

# BM25 constants (Robertson/Sparck-Jones defaults).
_BM25_K1 = 1.5
_BM25_B = 0.75


def tokenize(text: str) -> List[str]:
    """Lowercase word/version tokens, with the `v` version prefix normalised away.

    Version strings stay whole (`6.18.21` is one token, not three), and a
    release written `v6.18.21` in a release note tokenises the same as `6.18.21`
    typed by a user. Version identity is the single most load-bearing match in
    this domain, so it must not hinge on the prefix convention of the source.
    """
    out = []
    for tok in _TOKEN_RE.findall((text or "").lower()):
        if len(tok) > 1 and tok[0] == "v" and tok[1].isdigit():
            tok = tok[1:]
        out.append(tok)
    return out


def doc_text(doc: dict) -> str:
    """The text a reranker scores. Mirrors what the answer synthesiser sees."""
    parts = [
        doc.get("title", ""),
        doc.get("detail", "") or doc.get("text", "") or "",
        doc.get("top_comment", "") or "",
        doc.get("subreddit", "") or "",
    ]
    return " ".join(p for p in parts if p)


class Reranker:
    """Base interface. `spec` identifies the arm in a results table."""

    spec = "base"
    degraded = False  # set when a backend fell back to a weaker one

    def rank(self, query: str, docs: Sequence[dict], top_k: int = 4) -> List[dict]:
        raise NotImplementedError

    def scores(self, query: str, docs: Sequence[dict]) -> List[float]:
        """Per-document relevance scores, aligned with `docs`. For diagnostics."""
        raise NotImplementedError


class NoopReranker(Reranker):
    """The published behaviour: substring boost on the first four query tokens.

    Kept as the ablation arm that reproduces the paper's original ordering.
    Note it is deliberately given the *ranking* query it was originally given
    at the call site; the caller decides whether that is the rewrite or not.
    """

    spec = "none"

    def scores(self, query: str, docs: Sequence[dict]) -> List[float]:
        head = [w for w in (query or "").lower().split()[:4] if len(w) > 3]
        return [
            1.0 if any(w in (d.get("title", "") or "").lower() for w in head) else 0.0
            for d in docs
        ]

    def rank(self, query: str, docs: Sequence[dict], top_k: int = 4) -> List[dict]:
        s = self.scores(query, docs)
        boosted = [d for d, sc in zip(docs, s) if sc > 0]
        rest = [d for d, sc in zip(docs, s) if sc <= 0]
        return (boosted + rest)[:top_k]


class BM25Reranker(Reranker):
    """Okapi BM25 scored over the candidate pool itself.

    IDF comes from the pool rather than a global corpus. The pool is what the
    ranking decision is actually made over, it is small (tens of documents),
    and this keeps the reranker dependency-free and fully deterministic — which
    matters because it is the arm a reviewer can rerun without a model.
    """

    spec = "bm25"

    def __init__(self, k1: float = _BM25_K1, b: float = _BM25_B):
        self.k1 = k1
        self.b = b

    def scores(self, query: str, docs: Sequence[dict]) -> List[float]:
        if not docs:
            return []
        q_terms = tokenize(query)
        if not q_terms:
            return [0.0] * len(docs)

        doc_tokens = [tokenize(doc_text(d)) for d in docs]
        lengths = [len(t) for t in doc_tokens]
        avgdl = (sum(lengths) / len(lengths)) or 1.0
        n_docs = len(docs)

        # Document frequency of each query term within the pool.
        df: Dict[str, int] = {}
        for term in set(q_terms):
            df[term] = sum(1 for toks in doc_tokens if term in toks)

        out: List[float] = []
        for toks, dl in zip(doc_tokens, lengths):
            tf: Dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            for term in q_terms:
                f = tf.get(term, 0)
                if not f:
                    continue
                # Robertson/Sparck-Jones IDF, floored at 0. The floor matters
                # here: a term the whole pool shares (every candidate mentions
                # "update") carries no discriminating information, and without
                # the floor it would score negatively and actively demote the
                # documents that contain it.
                idf = max(0.0, math.log((n_docs - df[term] + 0.5) / (df[term] + 0.5)))
                denom = f + self.k1 * (1.0 - self.b + self.b * (dl / avgdl))
                score += idf * (f * (self.k1 + 1.0)) / denom
            out.append(score)
        return out

    def rank(self, query: str, docs: Sequence[dict], top_k: int = 4) -> List[dict]:
        s = self.scores(query, docs)
        # Stable sort on the negated score preserves the retriever's original
        # tier ordering (verified before community) among equal scores.
        order = sorted(range(len(docs)), key=lambda i: -s[i])
        return [docs[i] for i in order[:top_k]]


class EmbeddingReranker(Reranker):
    """Cosine similarity between the query and each document embedding.

    Uses the Ollama embeddings endpoint, so it inherits the project's
    "runs fully locally, no closed-model API calls" property. Embeddings are
    memoised per process because the same documents recur across the retry
    loop and across systems sharing a candidate pool.
    """

    def __init__(self, model: str = DEFAULT_EMBED_MODEL,
                 host: str = "http://localhost:11434", timeout: int = 60):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._cache: Dict[str, List[float]] = {}

    @property
    def spec(self) -> str:  # type: ignore[override]
        return f"embed:{self.model}"

    def available(self) -> bool:
        try:
            self._embed("probe")
            return True
        except Exception:  # noqa: BLE001 — availability probe, reason is irrelevant
            return False

    def _fetch_embedding(self, text: str) -> List[float]:
        """One embedding call to Ollama. Overridden in tests to avoid network."""
        payload = json.dumps({"model": self.model, "prompt": text}).encode()
        req = urllib.request.Request(
            f"{self.host}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode())
        vec = body.get("embedding") or []
        if not vec:
            raise RuntimeError(f"empty embedding from {self.model}")
        return vec

    def _embed(self, text: str) -> List[float]:
        """Memoised embedding. The same documents recur across retry cycles."""
        key = (text or "")[:4000]
        if key not in self._cache:
            self._cache[key] = self._fetch_embedding(key)
        return self._cache[key]

    @staticmethod
    def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    def scores(self, query: str, docs: Sequence[dict]) -> List[float]:
        if not docs:
            return []
        q = self._embed(query)
        return [self._cosine(q, self._embed(doc_text(d))) for d in docs]

    def rank(self, query: str, docs: Sequence[dict], top_k: int = 4) -> List[dict]:
        s = self.scores(query, docs)
        order = sorted(range(len(docs)), key=lambda i: -s[i])
        return [docs[i] for i in order[:top_k]]


class _FallbackReranker(Reranker):
    """An embedding reranker that silently could not run, reported honestly.

    Delegates to BM25 but keeps `embed:<model>` visible in `requested_spec`
    and sets `degraded`, so a results table can never claim a semantic run
    that did not happen.
    """

    def __init__(self, requested_spec: str, reason: str):
        self.requested_spec = requested_spec
        self.reason = reason
        self.degraded = True
        self._inner = BM25Reranker()

    @property
    def spec(self) -> str:  # type: ignore[override]
        return f"bm25(fallback from {self.requested_spec})"

    def scores(self, query: str, docs: Sequence[dict]) -> List[float]:
        return self._inner.scores(query, docs)

    def rank(self, query: str, docs: Sequence[dict], top_k: int = 4) -> List[dict]:
        return self._inner.rank(query, docs, top_k)


_RERANKER_CACHE: Dict[str, Reranker] = {}


def get_reranker(spec: Optional[str] = None) -> Reranker:
    """Process-wide memoised `make_reranker`.

    `EmbeddingReranker` caches embeddings per instance, and `make_reranker`
    spends one extra embedding call on the availability probe. Building a
    reranker per retrieval therefore threw the cache away before it could ever
    be hit and paid the probe on every query -- an eval of 50 questions across
    2 systems made ~50x2x(pool+2) Ollama round trips instead of reusing work.
    Callers on the hot path should use this; `make_reranker` stays available
    for tests and ablations that need a fresh instance.
    """
    key = (spec or DEFAULT_SPEC or "bm25").strip().lower()
    if key not in _RERANKER_CACHE:
        _RERANKER_CACHE[key] = make_reranker(key)
    return _RERANKER_CACHE[key]


def make_reranker(spec: Optional[str] = None) -> Reranker:
    """Build a reranker from a spec string.

    Accepted: "none", "bm25", "embed", "embed:<model>". Unknown specs raise
    rather than defaulting, so a typo in an ablation sweep fails loudly instead
    of quietly measuring the wrong arm.
    """
    spec = (spec or DEFAULT_SPEC or "bm25").strip().lower()
    if spec in ("none", "off", "noop"):
        return NoopReranker()
    if spec in ("bm25", "lexical"):
        return BM25Reranker()
    if spec == "embed" or spec.startswith("embed:"):
        model = spec.split(":", 1)[1] if ":" in spec else DEFAULT_EMBED_MODEL
        r = EmbeddingReranker(model=model)
        if r.available():
            return r
        return _FallbackReranker(f"embed:{model}", "ollama embedding model unavailable")
    raise ValueError(
        f"unknown rerank spec {spec!r} (expected none|bm25|embed|embed:<model>)"
    )
