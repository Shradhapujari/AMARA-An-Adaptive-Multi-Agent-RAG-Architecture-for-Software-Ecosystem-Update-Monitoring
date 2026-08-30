"""
Tests for eval_harness/generators.py — the systems under test.

The point of these tests is the *fairness* property the answer metrics depend
on: the multi-agent arm and the single-agent baseline must synthesise from the
identical prompt, so a difference in judged answer quality is attributable to
the retrieval pipeline rather than to prompt wording or model choice.

They are offline. The generators are built with `object.__new__` and stubbed
collaborators instead of real agents, so no Ollama call, no releasetrain.io
request, and no 4.9 GB model pull is involved.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness import generators as G  # noqa: E402
from eval_harness.providers import LLMError  # noqa: E402


DOCS = [
    {"title": "Firefox 149.0.1 released", "detail": "Security fixes for tabs.",
     "source": "releases", "url": "u1"},
    {"title": "Firefox crash on startup", "detail": "Reports after 149 update.",
     "source": "reddit_live", "url": "u2"},
    {"title": "Unrelated kernel advisory", "detail": "erofs fix.",
     "source": "cve", "url": "u3"},
]
QUERY = "What is the latest Firefox release?"


class CapturingClient:
    """LLMClient stand-in that records the prompt it was asked to complete."""

    spec = "ollama:stub"

    def __init__(self, reply="stub answer", raises=False, avail=True):
        self.prompts = []
        self.reply = reply
        self.raises = raises
        self.avail = avail

    def available(self):
        return self.avail

    def generate(self, prompt, system=None, temperature=0.0, max_tokens=1024):
        self.prompts.append(prompt)
        if self.raises:
            raise LLMError("stub backend down")
        return self.reply


def _fake_marag_module():
    """`_silenced` only needs an object whose pause/bar it can swap."""
    return types.SimpleNamespace(pause=lambda *a, **k: None,
                                 bar=lambda *a, **k: None)


def _single_agent(client, top_k=2):
    gen = object.__new__(G.SingleAgentGenerator)
    gen.marag = _fake_marag_module()
    gen.retriever = types.SimpleNamespace(run=lambda q, top_k=4, original_query=None: DOCS)
    gen.top_k = top_k
    gen.client = client
    return gen


def _marag(synth, top_k=2, template="TEMPLATE ANSWER", quality=0.7):
    gen = object.__new__(G.MultiAgentRAGGenerator)
    gen.marag = _fake_marag_module()
    gen.rewriter = types.SimpleNamespace(
        run=lambda q: {"rewritten": q + " latest version release notes"})
    gen.retriever = types.SimpleNamespace(run=lambda q, top_k=4, original_query=None: DOCS)
    gen.evaluator = types.SimpleNamespace(
        run=lambda docs, q: {"answer": template, "quality": quality})
    gen.top_k = top_k
    gen.synth = synth
    gen.name = "marag" if synth is None else "marag_llm"
    return gen


# ── the shared prompt ────────────────────────────────────────────────────

def test_prompt_contains_question_and_only_top_k_sources():
    prompt = G.build_synthesis_prompt(QUERY, DOCS, top_k=2)
    assert QUERY in prompt
    assert G.SYNTHESIS_INSTRUCTION in prompt
    assert "Firefox 149.0.1 released" in prompt
    assert "Firefox crash on startup" in prompt
    # top_k=2 must not leak the third doc into the context.
    assert "Unrelated kernel advisory" not in prompt


def test_prompt_reports_empty_retrieval_rather_than_an_empty_context():
    assert "No documents retrieved." in G.build_synthesis_prompt(QUERY, [], top_k=4)


def test_prompt_accepts_both_raw_and_normalized_docs():
    """Raw pipeline docs carry `detail`; harness-normalized docs carry `text`."""
    raw = G.build_synthesis_prompt(QUERY, [DOCS[0]], top_k=1)
    norm = G.build_synthesis_prompt(QUERY, [G.normalize_doc(DOCS[0])], top_k=1)
    assert "Security fixes for tabs." in raw
    assert "Security fixes for tabs." in norm


# ── the fairness property ────────────────────────────────────────────────

def test_both_arms_synthesise_from_the_identical_prompt():
    """
    The regression test for the answer-metric confound: if these prompts ever
    diverge, a marag_llm vs single_agent answer-quality difference stops being
    evidence about retrieval.
    """
    base_client, marag_client = CapturingClient(), CapturingClient()
    _single_agent(base_client).generate(QUERY)
    _marag(marag_client).generate(QUERY)
    assert base_client.prompts == marag_client.prompts != []


def test_marag_llm_answer_comes_from_the_synthesiser_and_keeps_the_template():
    client = CapturingClient(reply="Firefox 149.0.1 is the latest release.")
    out = _marag(client).generate(QUERY)
    assert out["answer"] == "Firefox 149.0.1 is the latest release."
    # The published template answer is retained for audit, not discarded.
    assert out["template_answer"] == "TEMPLATE ANSWER"
    assert out["synth_model"] == "ollama:stub"


def test_template_arm_is_the_published_system_unchanged():
    out = _marag(None).generate(QUERY)
    assert out["answer"] == "TEMPLATE ANSWER"
    assert "template_answer" not in out and "synth_model" not in out
    assert out["self_quality"] == 0.7
    assert out["rewritten_query"].startswith(QUERY)


def test_retrieval_is_identical_across_the_two_arms():
    """Switching the answer path must not move the IR metrics."""
    a = _marag(None).generate(QUERY)
    b = _marag(CapturingClient()).generate(QUERY)
    assert [d["doc_id"] for d in a["docs"]] == [d["doc_id"] for d in b["docs"]]


def test_synthesiser_failure_is_reported_not_silently_templated():
    out = _marag(CapturingClient(raises=True)).generate(QUERY)
    assert out["answer"].startswith("[generation error:")
    assert out["template_answer"] == "TEMPLATE ANSWER"


def test_availability_follows_the_synthesiser():
    assert _marag(None).available() is True
    assert _marag(CapturingClient(avail=False)).available() is False


# ── spec grammar ─────────────────────────────────────────────────────────

def test_spec_grammar_attaches_a_synthesiser_only_when_asked(monkeypatch):
    built = []

    class Recorder:
        def __init__(self, top_k=4, synth=None):
            built.append((top_k, synth))
            self.name = "marag" if synth is None else "marag_llm"

    monkeypatch.setattr(G, "MultiAgentRAGGenerator", Recorder)
    gens = G.build_generators(["marag", "marag:ollama:mistral"], top_k=3)

    assert [g.name for g in gens] == ["marag", "marag_llm"]
    assert built[0] == (3, None)
    assert built[1][0] == 3 and built[1][1].spec == "ollama:mistral"


def test_unknown_spec_is_rejected():
    with pytest.raises(ValueError):
        G.build_generators(["marag_llm"])
