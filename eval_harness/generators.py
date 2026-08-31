"""
Generator adapters — the systems under test.
============================================
Every generator implements:

    gen.generate(query) -> {
        "answer":   str,                 # final natural-language answer
        "docs":     [doc, ...],          # retrieved docs (ranked); [] if no retrieval
        "self_quality": float|None,      # the system's own heuristic score, if any
        "pool":     [doc, ...],          # pre-rerank candidates; [] if not applicable
    }

`pool` is what the reranker was given, before it cut to top_k. It separates a
ranking failure (the document was fetched and buried) from a fetch failure (the
document was never retrieved at all) -- two defects with different fixes that
the final ranked list cannot tell apart.

doc is a dict with at least {"doc_id", "title", "text", "source", "url"}.

Systems:
  - MultiAgentRAGGenerator        : full 4-agent pipeline (Rewriter -> Retriever -> RLAIF Evaluator)
  - SingleAgentGenerator  : the paper's baseline (raw query -> keyword retrieval -> 1 LLM call)
  - RawLLMGenerator       : no retrieval, ask a model directly (GPT/Claude/Llama/...)
                            -> this is the "compare against other models" column

Answer-metric fairness
----------------------
The multi-agent pipeline's own answer is a *template* assembled by
`EvaluatorAgent` (headers, bullet lists, source tags); the single-agent
baseline's answer is LLM prose. Scoring those two against each other with an
LLM judge measures answer *format* as much as answer *content*, so a
head-to-head on faithfulness/correctness between `marag` and `single_agent`
is confounded by construction.

The `marag_llm` arm removes that confound: same multi-agent retrieval, but the
answer is synthesised from the retrieved docs through `build_synthesis_prompt`
with the same model as the baseline. Then the only difference left between the
two arms is the retrieval pipeline, which is the claim under test. `marag`
stays available because it is the system the paper describes; `marag_llm`
keeps its template answer under `template_answer` so nothing is lost.

The Multi-Agent RAG System pipeline (`multiagent_rag_v3.py`) is a noisy CLI script; we import it
and silence stdout + the artificial `pause()`/`bar()` sleeps so it runs fast and
clean in batch.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import sys
from typing import List, Dict, Optional

from .providers import LLMClient, make_client, LLMError

# Make the project root importable regardless of where the harness is run from.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def doc_id(d: dict) -> str:
    """Stable id for a retrieved doc, used for relevance judgments / qrels."""
    key = (d.get("url") or "").strip() or (d.get("title", "") + "|" + d.get("source", ""))
    return hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:12]


def normalize_doc(d: dict) -> dict:
    """Project an Multi-Agent RAG System doc dict into the harness's canonical shape."""
    text = d.get("detail") or d.get("top_comment") or ""
    return {
        "doc_id": doc_id(d),
        "title": d.get("title", ""),
        "text": text,
        "source": d.get("source", "?"),
        "url": d.get("url", ""),
        "subreddit": d.get("subreddit", ""),
        "date": d.get("date", ""),
    }


@contextlib.contextmanager
def _silenced(mod):
    """Suppress stdout and the Multi-Agent RAG System module's pause()/bar() side effects."""
    saved_pause = getattr(mod, "pause", None)
    saved_bar = getattr(mod, "bar", None)
    mod.pause = lambda *a, **k: None
    mod.bar = lambda *a, **k: None
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            yield
    finally:
        if saved_pause is not None:
            mod.pause = saved_pause
        if saved_bar is not None:
            mod.bar = saved_bar


# ─────────────────────────────────────────────────────────────────────────
# Symmetric answer synthesis
# ─────────────────────────────────────────────────────────────────────────
# Every arm that turns retrieved docs into prose goes through the function
# below, so a difference in answer scores between two arms cannot be an
# artefact of a different prompt. The model is the caller's choice; pass the
# same one to both arms to keep that comparison clean too.

SYNTHESIS_INSTRUCTION = (
    "You are a software-update assistant. Answer the question using ONLY the "
    "sources below. Be concise (2-3 sentences). If the sources do not contain "
    "the answer, say so."
)


def build_synthesis_prompt(query: str, docs: List[dict], top_k: int) -> str:
    """The one synthesis prompt, shared by every doc-grounded arm."""
    ctx = "\n".join(
        f"- [{d.get('source','?')}] {d.get('title','')}: "
        f"{(d.get('detail') or d.get('text') or '')[:200]}"
        for d in docs[:top_k]
    ) or "No documents retrieved."
    return (
        f"{SYNTHESIS_INSTRUCTION}\n\n"
        f"Question: {query}\n\nSources:\n{ctx}\n\nAnswer:"
    )


class Generator:
    name = "base"

    def available(self) -> bool:
        return True

    def generate(self, query: str) -> Dict:
        raise NotImplementedError


class MultiAgentRAGGenerator(Generator):
    """
    Full multi-agent pipeline from multiagent_rag_v3.py.

    `synth=None` is the published system: the answer is EvaluatorAgent's
    template. Passing a client switches the answer to LLM prose synthesised
    from the same retrieved docs with `build_synthesis_prompt` — the arm that
    is answer-comparable to SingleAgentGenerator. Retrieval is identical
    either way, so IR metrics do not move between the two arms.
    """

    name = "marag"

    def __init__(self, top_k: int = 4, synth: Optional[LLMClient] = None):
        import multiagent_rag_v3 as marag
        self.marag = marag
        self.rewriter = marag.QueryRewriterAgent()
        self.retriever = marag.RetrieverAgent()
        self.evaluator = marag.EvaluatorAgent()
        self.top_k = top_k
        self.synth = synth
        if synth is not None:
            self.name = "marag_llm"

    def available(self) -> bool:
        return True if self.synth is None else self.synth.available()

    def generate(self, query: str) -> Dict:
        with _silenced(self.marag):
            rewrite = self.rewriter.run(query)
            docs = self.retriever.run(rewrite["rewritten"], top_k=self.top_k,
                                      original_query=query)
            result = self.evaluator.run(docs, query)
        template_answer = result.get("answer", "")
        answer = template_answer
        if self.synth is not None:
            try:
                answer = self.synth.generate(
                    build_synthesis_prompt(query, docs, self.top_k),
                    temperature=0.0, max_tokens=400)
            except LLMError as e:
                answer = f"[generation error: {e}]"
        out = {
            "answer": answer,
            "docs": [normalize_doc(d) for d in docs],
            "self_quality": result.get("quality"),
            "rewritten_query": rewrite.get("rewritten", ""),
            "pool": [normalize_doc(d) for d in getattr(self.retriever, "last_pool", [])],
            "rerank_spec": getattr(self.retriever, "last_rerank_spec", ""),
            "rerank_degraded": getattr(self.retriever, "last_rerank_degraded", False),
        }
        if self.synth is not None:
            # The published template answer, kept for audit: the synthesised
            # arm replaces what is scored, not what the system produced.
            out["template_answer"] = template_answer
            out["synth_model"] = self.synth.spec
        return out


class SingleAgentGenerator(Generator):
    """
    Paper's baseline: raw query, keyword retrieval (no rewriting, no CVE agent,
    no RLAIF), and a single LLM synthesis call. Uses Multi-Agent RAG System's retriever but feeds
    it the *raw* query and a plain synthesis prompt — i.e. the multi-agent
    machinery stripped away.
    """

    name = "single_agent"

    def __init__(self, client: Optional[LLMClient] = None, top_k: int = 4):
        import multiagent_rag_v3 as marag
        self.marag = marag
        self.retriever = marag.RetrieverAgent()
        self.top_k = top_k
        self.client = client or make_client("ollama:mistral")

    def available(self) -> bool:
        return self.client.available()

    def generate(self, query: str) -> Dict:
        with _silenced(self.marag):
            docs = self.retriever.run(query, top_k=self.top_k, original_query=query)
        prompt = build_synthesis_prompt(query, docs, self.top_k)
        try:
            answer = self.client.generate(prompt, temperature=0.0, max_tokens=400)
        except LLMError as e:
            answer = f"[generation error: {e}]"
        return {
            "answer": answer,
            "docs": [normalize_doc(d) for d in docs],
            "self_quality": None,
            # The baseline shares RetrieverAgent with the multi-agent arm, so it
            # is reranked by the same backend. That is precisely why it is not a
            # rerank-independent control, and why the pool is logged for it too.
            "pool": [normalize_doc(d) for d in getattr(self.retriever, "last_pool", [])],
            "rerank_spec": getattr(self.retriever, "last_rerank_spec", ""),
            "rerank_degraded": getattr(self.retriever, "last_rerank_degraded", False),
        }


class RawLLMGenerator(Generator):
    """No retrieval — ask a model directly. The 'other models' comparison column."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.name = f"raw:{client.spec}"

    def available(self) -> bool:
        return self.client.available()

    def generate(self, query: str) -> Dict:
        prompt = (
            "You are a software-update assistant. Answer the user's question about "
            "software releases, bugs, or security as accurately as you can in 2-3 "
            "sentences. If you are unsure, say so rather than inventing details.\n\n"
            f"Question: {query}\n\nAnswer:"
        )
        try:
            answer = self.client.generate(prompt, temperature=0.0, max_tokens=400)
        except LLMError as e:
            answer = f"[generation error: {e}]"
        return {"answer": answer, "docs": [], "self_quality": None, "pool": []}



class SelfReflectiveGenerator(Generator):
    """Self-RAG / CRAG-style critique loop over this project's retrieval.

    A reimplementation of the published *mechanisms*, not the published systems:
    neither Self-RAG's reflection-token checkpoint nor CRAG's fine-tuned
    retrieval evaluator is used. See eval_harness/selfreflective.py for what is
    reimplemented and where it deviates.

    Retrieval is the same RetrieverAgent every other doc-grounded arm uses, fed
    the raw question, and the drafting prompt is the shared one -- so a
    difference against `single_agent` is the critique loop and nothing else.
    """

    def __init__(self, client: Optional[LLMClient] = None, top_k: int = 4,
                 keep_partial: bool = True):
        import multiagent_rag_v3 as marag
        from .selfreflective import SelfReflectiveRAG
        self.marag = marag
        self.retriever = marag.RetrieverAgent()
        self.top_k = top_k
        self.client = client or make_client("ollama:llama3.1")
        self.engine = SelfReflectiveRAG(self.client, top_k=top_k,
                                        keep_partial=keep_partial)
        self.name = "selfreflective"

    def available(self) -> bool:
        return self.client.available()

    def generate(self, query: str) -> Dict:
        with _silenced(self.marag):
            docs = self.retriever.run(query, top_k=self.top_k,
                                      original_query=query)
            pool = list(getattr(self.retriever, "last_pool", []) or [])
        out = self.engine.run(query, docs, build_synthesis_prompt)
        # `docs` stays the full retrieved list rather than the critique-filtered
        # one: IR metrics score what the system retrieved, and reporting only the
        # kept documents would flatter precision by hiding the discards.
        return {
            "answer": out["answer"],
            "docs": [normalize_doc(d) for d in docs],
            "self_quality": None,
            "pool": [normalize_doc(d) for d in pool],
            "trace": out["trace"],
        }


def build_generators(specs: List[str], top_k: int = 4) -> List[Generator]:
    """
    Build generators from short specs:
      "marag"                      -> MultiAgentRAGGenerator (template answer)
      "marag:ollama:mistral"       -> same pipeline, answer synthesised by that
                                      model through the shared prompt, so its
                                      answer scores are comparable to
                                      single_agent's (reported as "marag_llm")
      "selfreflective"             -> Self-RAG/CRAG-style critique loop over the
                                      same retrieval (reimplementation, not the
                                      published checkpoints)
      "selfreflective:ollama:llama3.1" -> same, with a chosen critic/synthesis model
      "single_agent"               -> SingleAgentGenerator (mistral synthesis)
      "single_agent:ollama:llama3.1" -> SingleAgentGenerator with a given model
      "raw:ollama:llama3.1"        -> RawLLMGenerator over that model
      "raw:openai:gpt-4o"          -> RawLLMGenerator over GPT-4o (if key present)
    """
    gens: List[Generator] = []
    for spec in specs:
        if spec == "marag":
            gens.append(MultiAgentRAGGenerator(top_k=top_k))
        elif spec.startswith("marag:"):
            gens.append(MultiAgentRAGGenerator(
                top_k=top_k, synth=make_client(spec.split(":", 1)[1])))
        elif spec == "single_agent":
            gens.append(SingleAgentGenerator(top_k=top_k))
        elif spec.startswith("single_agent:"):
            gens.append(SingleAgentGenerator(make_client(spec.split(":", 1)[1]), top_k))
        elif spec == "selfreflective":
            gens.append(SelfReflectiveGenerator(top_k=top_k))
        elif spec.startswith("selfreflective:"):
            gens.append(SelfReflectiveGenerator(
                make_client(spec.split(":", 1)[1]), top_k))
        elif spec.startswith("raw:"):
            gens.append(RawLLMGenerator(make_client(spec.split(":", 1)[1])))
        else:
            raise ValueError(f"unknown generator spec: {spec}")
    return gens
