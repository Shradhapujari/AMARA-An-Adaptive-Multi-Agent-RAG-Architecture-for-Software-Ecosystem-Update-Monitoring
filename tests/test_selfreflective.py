"""
Tests for the Self-RAG / CRAG-style baseline arm.

Offline: the LLM client is stubbed, so the critique loop is exercised without
Ollama. What matters here is the control flow, because this arm's whole purpose
is to abstain where the other arms guess — if the abstention path is wrong, the
arm silently becomes a slower copy of `single_agent`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness.providers import LLMClient, LLMError  # noqa: E402
from eval_harness.selfreflective import (  # noqa: E402
    DECLINE_TEXT, SelfReflectiveRAG, _one_word, doc_context,
)

DOCS = [
    {"title": "Firefox 149.0.1 release notes", "detail": "security fixes",
     "source": "releases"},
    {"title": "Red Hat kernel advisory", "detail": "unrelated CVE",
     "source": "releases"},
]


class StubClient(LLMClient):
    """Replies from a scripted queue; records every prompt it was given."""

    backend = "stub"

    def __init__(self, replies):
        super().__init__("stub")
        self.replies = list(replies)
        self.prompts = []

    def _generate(self, prompt, system, temperature, max_tokens):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else "RELEVANT"


class FailingClient(LLMClient):
    backend = "stub"

    def __init__(self):
        super().__init__("stub")

    def _generate(self, prompt, system, temperature, max_tokens):
        raise RuntimeError("backend down")


def prompt_fn(query, docs, top_k):
    return f"Q:{query} N:{len(docs)}"


# ------------------------------------------------------------------- parsing

@pytest.mark.parametrize("reply,expected", [
    ("RELEVANT", "RELEVANT"),
    ("  irrelevant  ", "IRRELEVANT"),
    ("**SUPPORTED**", "SUPPORTED"),
    ("Relevant.", "RELEVANT"),
    ("1. RELEVANT", "RELEVANT"),
    ("", ""),
    ("...", ""),
])
def test_one_word_extracts_the_verdict(reply, expected):
    assert _one_word(reply) == expected


def test_doc_context_handles_empty_and_missing_fields():
    assert "No documents retrieved" in doc_context([])
    assert "releases" in doc_context([DOCS[0]])


# ------------------------------------------------------------------ critique

def test_relevant_verdict_keeps_the_document():
    e = SelfReflectiveRAG(StubClient(["RELEVANT"]))
    assert e.is_relevant("Firefox version?", DOCS[0]) is True


def test_irrelevant_verdict_discards_the_document():
    e = SelfReflectiveRAG(StubClient(["IRRELEVANT"]))
    assert e.is_relevant("Firefox version?", DOCS[1]) is False


def test_a_failed_critique_keeps_the_document():
    """Failing open is the conservative direction: it makes this arm behave more
    like the non-abstaining arms, so it cannot manufacture its own advantage."""
    e = SelfReflectiveRAG(FailingClient())
    assert e.is_relevant("Firefox version?", DOCS[0]) is True


def test_support_verdict_defaults_to_partial_when_the_backend_fails():
    e = SelfReflectiveRAG(FailingClient())
    assert e.support_verdict("q", DOCS, "answer") == "PARTIAL"


def test_support_verdict_defaults_to_partial_on_an_empty_reply():
    e = SelfReflectiveRAG(StubClient([""]))
    assert e.support_verdict("q", DOCS, "answer") == "PARTIAL"


# -------------------------------------------------------------- control flow

def test_declines_when_no_document_survives_the_relevance_critique():
    e = SelfReflectiveRAG(StubClient(["IRRELEVANT", "IRRELEVANT"]))
    out = e.run("Firefox version?", DOCS, prompt_fn)
    assert out["answer"] == DECLINE_TEXT
    assert out["kept"] == []
    assert out["trace"]["action"] == "decline_no_relevant"
    assert out["trace"]["n_relevant"] == 0


def test_declines_when_the_draft_is_unsupported():
    e = SelfReflectiveRAG(StubClient(["RELEVANT", "IRRELEVANT",
                                      "a draft answer", "UNSUPPORTED"]))
    out = e.run("Firefox version?", DOCS, prompt_fn)
    assert out["answer"] == DECLINE_TEXT
    assert out["trace"]["action"] == "decline_unsupported"
    assert out["trace"]["support"] == "UNSUPPORTED"


def test_accepts_a_supported_draft():
    e = SelfReflectiveRAG(StubClient(["RELEVANT", "IRRELEVANT",
                                      "Firefox 149.0.1 is latest.", "SUPPORTED"]))
    out = e.run("Firefox version?", DOCS, prompt_fn)
    assert out["answer"] == "Firefox 149.0.1 is latest."
    assert out["trace"]["action"] == "accept"
    assert len(out["kept"]) == 1


def test_partial_support_is_accepted_by_default_and_rejectable():
    script = ["RELEVANT", "IRRELEVANT", "draft", "PARTIAL"]
    lenient = SelfReflectiveRAG(StubClient(list(script)))
    assert lenient.run("q", DOCS, prompt_fn)["answer"] == "draft"

    strict = SelfReflectiveRAG(StubClient(list(script)), keep_partial=False)
    assert strict.run("q", DOCS, prompt_fn)["answer"] == DECLINE_TEXT


def test_only_top_k_documents_are_critiqued():
    """One critique call per candidate, capped at top_k — cost is bounded."""
    docs = DOCS * 5
    stub = StubClient(["RELEVANT"] * 2 + ["draft", "SUPPORTED"])
    e = SelfReflectiveRAG(stub, top_k=2)
    e.run("q", docs, prompt_fn)
    # 2 relevance critiques + 1 draft + 1 support critique
    assert len(stub.prompts) == 4


def test_generation_error_is_reported_not_silently_declined():
    class DraftFails(LLMClient):
        backend = "stub"
        def __init__(self):
            super().__init__("stub")
            self.n = 0
        def _generate(self, prompt, system, temperature, max_tokens):
            self.n += 1
            if self.n <= 2:
                return "RELEVANT"
            raise RuntimeError("draft failed")

    out = SelfReflectiveRAG(DraftFails()).run("q", DOCS, prompt_fn)
    assert out["trace"]["action"] == "generation_error"
    assert "generation error" in out["answer"]


def test_empty_retrieval_declines():
    out = SelfReflectiveRAG(StubClient([])).run("q", [], prompt_fn)
    assert out["answer"] == DECLINE_TEXT
    assert out["trace"]["n_retrieved"] == 0


def test_the_shared_synthesis_prompt_is_used_for_drafting():
    """Drafting must use the same prompt as the other arms, or a prompt
    difference is confounded with the mechanism under test."""
    stub = StubClient(["RELEVANT", "IRRELEVANT", "draft", "SUPPORTED"])
    SelfReflectiveRAG(stub).run("my question", DOCS, prompt_fn)
    assert any(p.startswith("Q:my question") for p in stub.prompts)


def test_decline_text_reads_as_an_abstention_to_the_benchmark_scorer():
    """CRAG-style scoring must label a decline `missing`, not `incorrect`."""
    from eval_harness.benchmarks import is_abstention
    assert is_abstention(DECLINE_TEXT, strong_only=True) is True
