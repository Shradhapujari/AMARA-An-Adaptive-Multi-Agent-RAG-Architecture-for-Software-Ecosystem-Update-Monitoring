"""
Tests for rerank.py — the candidate reranking stage of the Retriever Agent.

These are offline: the BM25 and noop arms need no model, and the embedding arm
is exercised through a stubbed embedder rather than a live Ollama call, so the
suite runs in CI without a GPU or a pulled model.

The central test is `test_rewrite_breaks_noop_ranking_original_query_fixes_it`,
which encodes the defect from eval_harness/FINDINGS.md as a regression test.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rerank  # noqa: E402


# A candidate pool shaped like a real one: the vendor-specific document the
# user actually wants, plus generic kernel advisories that the live API returns
# for almost any query.
POOL = [
    {"title": "Red Hat v7.2.0 kernel vulnerability erofs",
     "detail": "In the Linux kernel the following vulnerability has been resolved"},
    {"title": "Linux v6.18.21 kernel net vulnerability",
     "detail": "kernel networking fix"},
    {"title": "G6 Bullet firmware instability reports",
     "detail": "Ubiquiti G6 Bullet camera dropping connection after firmware update",
     "subreddit": "Ubiquiti"},
    {"title": "Considering two Unifi EV Station Lite chargers",
     "detail": "load management group 60A split", "subreddit": "Ubiquiti"},
]

ORIGINAL = "G6 Bullet unstable?"
REWRITTEN = "Unstable behavior in G6 Bullet software: known issues or updates for release"
WANTED = "G6 Bullet firmware instability reports"


class StubEmbedder(rerank.EmbeddingReranker):
    """EmbeddingReranker with the network replaced by a bag-of-words vector.

    Keeps the real cosine/ranking code under test while removing the Ollama
    dependency. Not a semantic model — it only has to be deterministic and
    to prefer overlapping vocabulary.
    """

    VOCAB = ["g6", "bullet", "unstable", "instability", "kernel",
             "vulnerability", "ubiquiti", "unifi", "chargers", "firmware"]

    def __init__(self):
        super().__init__(model="stub")
        self.calls = 0

    def _fetch_embedding(self, text):
        self.calls += 1
        toks = rerank.tokenize(text)
        return [float(toks.count(v)) for v in self.VOCAB]


def test_tokenize_keeps_version_strings_intact():
    assert "6.18.21" in rerank.tokenize("Linux v6.18.21 released")
    assert "149.0.1" in rerank.tokenize("Firefox v149.0.1")


def test_doc_text_concatenates_the_fields_the_synthesiser_sees():
    text = rerank.doc_text({"title": "T", "detail": "D", "top_comment": "C",
                            "subreddit": "S"})
    assert all(part in text for part in ("T", "D", "C", "S"))


def test_doc_text_tolerates_missing_and_none_fields():
    assert rerank.doc_text({}) == ""
    assert rerank.doc_text({"title": None, "detail": "D"}) == "D"


@pytest.mark.parametrize("spec", ["none", "bm25"])
def test_original_query_ranks_the_relevant_document_first(spec):
    ranked = rerank.make_reranker(spec).rank(ORIGINAL, POOL, top_k=2)
    assert ranked[0]["title"] == WANTED


def test_rewrite_breaks_noop_ranking_original_query_fixes_it():
    """The FINDINGS.md defect, as a regression test.

    Ranking on the rewritten query promotes generic kernel advisories over the
    document the user asked about; ranking the same pool on the original query
    does not. If this ever stops failing for `none`, the rewrite has stopped
    being lossy and the reranking stage would need re-justifying.
    """
    noop = rerank.NoopReranker()
    on_rewrite = noop.rank(REWRITTEN, POOL, top_k=2)
    on_original = noop.rank(ORIGINAL, POOL, top_k=2)

    assert WANTED not in [d["title"] for d in on_rewrite]
    assert on_original[0]["title"] == WANTED


def test_bm25_is_robust_to_the_rewrite_that_breaks_the_noop_ranker():
    """BM25 sees the whole document and the whole query, not four tokens."""
    ranked = rerank.BM25Reranker().rank(REWRITTEN, POOL, top_k=2)
    assert ranked[0]["title"] == WANTED


def test_bm25_scores_are_deterministic():
    a = rerank.BM25Reranker().scores(ORIGINAL, POOL)
    b = rerank.BM25Reranker().scores(ORIGINAL, POOL)
    assert a == b


def test_bm25_ignores_terms_present_in_every_document():
    """A term in every pool document carries no discriminating information."""
    pool = [{"title": "update alpha"}, {"title": "update beta"}]
    scores = rerank.BM25Reranker().scores("update", pool)
    assert scores == [0.0, 0.0]


def test_embedding_reranker_ranks_by_cosine_and_caches_embeddings():
    stub = StubEmbedder()
    ranked = stub.rank(ORIGINAL, POOL, top_k=1)
    assert ranked[0]["title"] == WANTED

    calls_after_first = stub.calls
    stub.rank(ORIGINAL, POOL, top_k=1)
    # Same query, same pool: every embedding should come from the cache.
    assert stub.calls == calls_after_first


def test_cosine_handles_degenerate_vectors():
    cos = rerank.EmbeddingReranker._cosine
    assert cos([], [1.0]) == 0.0
    assert cos([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cos([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_empty_pool_returns_empty_for_every_backend():
    for spec in ("none", "bm25"):
        r = rerank.make_reranker(spec)
        assert r.rank(ORIGINAL, [], top_k=4) == []
        assert r.scores(ORIGINAL, []) == []


def test_rank_never_returns_more_than_top_k():
    assert len(rerank.make_reranker("bm25").rank(ORIGINAL, POOL, top_k=2)) == 2


def test_make_reranker_rejects_unknown_spec_rather_than_defaulting():
    """A typo in an ablation sweep must fail loudly, not measure another arm."""
    with pytest.raises(ValueError):
        rerank.make_reranker("embeddings")


def test_make_reranker_reads_spec_case_insensitively():
    assert rerank.make_reranker("BM25").spec == "bm25"


def test_fallback_reports_degradation_instead_of_claiming_a_semantic_run():
    fb = rerank._FallbackReranker("embed:nomic-embed-text", "model unavailable")
    assert fb.degraded is True
    assert "fallback" in fb.spec
    # It still ranks correctly — it is BM25 underneath.
    assert fb.rank(ORIGINAL, POOL, top_k=1)[0]["title"] == WANTED


def test_embed_spec_falls_back_when_ollama_is_unreachable(monkeypatch):
    monkeypatch.setattr(rerank.EmbeddingReranker, "available", lambda self: False)
    r = rerank.make_reranker("embed:does-not-exist")
    assert r.degraded is True
    assert "does-not-exist" in r.spec
