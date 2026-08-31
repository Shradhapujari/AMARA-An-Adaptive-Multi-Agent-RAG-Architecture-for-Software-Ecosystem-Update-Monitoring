"""
Tests for the pre-rerank candidate pool surfaced through the generators.

A reranker can only reorder documents it was handed. "The reranker buried the
answer" and "the fetch never found the answer" are different defects with
different fixes, and the final top_k cannot tell them apart — which is exactly
the question the 2026-08-30 ablation could not answer from its artifacts,
because only `doc_ids` was written.

`pool` closes that gap: every retrieval-backed arm reports what the reranker
saw, so pool recall (the ceiling any reranker could reach on that fetch) is
computable alongside recall@k.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness import generators as G  # noqa: E402

TOP_K_DOCS = [
    {"title": "Firefox 149.0.1 released", "detail": "Security fixes.",
     "source": "releases", "url": "u1"},
    {"title": "Firefox crash on startup", "detail": "Reports after 149.",
     "source": "reddit_live", "url": "u2"},
]
# What the retriever fetched before ranking cut it down — a superset.
POOL_DOCS = TOP_K_DOCS + [
    {"title": "Firefox 149 changelog", "detail": "Full notes.",
     "source": "releases", "url": "u3"},
    {"title": "Unrelated kernel advisory", "detail": "erofs fix.",
     "source": "cve", "url": "u4"},
]


class StubClient:
    spec = "ollama:stub"

    def available(self):
        return True

    def generate(self, prompt, system=None, temperature=0.0, max_tokens=1024):
        return "stub answer"


def _fake_marag_module():
    return types.SimpleNamespace(pause=lambda *a, **k: None,
                                 bar=lambda *a, **k: None)


def _retriever(spec="bm25", degraded=False, pool=POOL_DOCS):
    """A retriever stub that reports diagnostics the way RetrieverAgent does."""
    r = types.SimpleNamespace(
        run=lambda q, top_k=4, original_query=None: TOP_K_DOCS,
        last_pool=pool,
        last_rank_query="original",
        last_rerank_spec=spec,
        last_rerank_degraded=degraded,
    )
    return r


def _single_agent(**kw):
    gen = object.__new__(G.SingleAgentGenerator)
    gen.marag = _fake_marag_module()
    gen.retriever = _retriever(**kw)
    gen.top_k = 2
    gen.client = StubClient()
    return gen


def _marag(**kw):
    gen = object.__new__(G.MultiAgentRAGGenerator)
    gen.marag = _fake_marag_module()
    gen.rewriter = types.SimpleNamespace(run=lambda q: {"rewritten": q + " release notes"})
    gen.retriever = _retriever(**kw)
    gen.evaluator = types.SimpleNamespace(
        run=lambda docs, q: {"answer": "TEMPLATE", "quality": 0.7})
    gen.top_k = 2
    gen.synth = None
    return gen


# ── the pool is reported, and it is bigger than the ranked list ──────────

def test_marag_reports_the_pre_rerank_pool():
    out = _marag().generate("firefox?")
    assert [d["title"] for d in out["pool"]] == [d["title"] for d in POOL_DOCS]


def test_single_agent_reports_the_pre_rerank_pool_too():
    """The baseline shares RetrieverAgent, so it is reranked and must be logged."""
    out = _single_agent().generate("firefox?")
    assert [d["title"] for d in out["pool"]] == [d["title"] for d in POOL_DOCS]


def test_the_pool_is_a_superset_of_the_returned_documents():
    out = _marag().generate("firefox?")
    ranked = {d["doc_id"] for d in out["docs"]}
    pool = {d["doc_id"] for d in out["pool"]}
    assert ranked < pool


def test_pool_documents_are_normalised_like_ranked_ones():
    """They are judged by the same code path, so they need the same shape."""
    out = _marag().generate("firefox?")
    for d in out["pool"]:
        assert set(d) >= {"doc_id", "title", "text", "source", "url"}


def test_a_document_buried_by_ranking_is_visible_in_the_pool():
    """The distinguishing case: relevant doc fetched, then not returned."""
    out = _marag().generate("firefox?")
    ranked = {d["doc_id"] for d in out["docs"]}
    buried = [d for d in out["pool"] if d["doc_id"] not in ranked]
    assert [d["title"] for d in buried] == ["Firefox 149 changelog",
                                            "Unrelated kernel advisory"]


# ── the arm is reported ──────────────────────────────────────────────────

def test_the_active_rerank_backend_is_reported():
    """Which arm a row belongs to must come from the run, not from memory."""
    assert _marag(spec="embed:nomic-embed-text").generate("q")["rerank_spec"] \
        == "embed:nomic-embed-text"


def test_a_degraded_backend_is_reported_as_degraded():
    """An embed arm that silently fell back to BM25 must not read as embed."""
    out = _marag(spec="bm25(fallback from embed:nomic-embed-text)",
                 degraded=True).generate("q")
    assert out["rerank_degraded"] is True
    assert "fallback" in out["rerank_spec"]


# ── degenerate cases ─────────────────────────────────────────────────────

def test_an_empty_pool_is_reported_as_empty_not_missing():
    out = _marag(pool=[]).generate("q")
    assert out["pool"] == []


def test_a_retrieval_free_arm_reports_an_empty_pool():
    """RawLLMGenerator has no retrieval; the key must still be present."""
    gen = G.RawLLMGenerator(StubClient())
    assert gen.generate("q")["pool"] == []


def test_a_retriever_without_diagnostics_does_not_break_the_run():
    """Older stubs and any future retriever lacking the attribute still work."""
    gen = object.__new__(G.SingleAgentGenerator)
    gen.marag = _fake_marag_module()
    gen.retriever = types.SimpleNamespace(
        run=lambda q, top_k=4, original_query=None: TOP_K_DOCS)
    gen.top_k = 2
    gen.client = StubClient()
    out = gen.generate("q")
    assert out["pool"] == []
    assert out["rerank_spec"] == ""
