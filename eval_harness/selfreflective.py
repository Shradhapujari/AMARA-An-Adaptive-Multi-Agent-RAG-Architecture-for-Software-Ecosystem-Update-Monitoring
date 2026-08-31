"""
A self-reflective / corrective RAG baseline, reimplemented over our retrieval.
=============================================================================

**This is not Self-RAG and it is not CRAG.** It is a reimplementation of the
inference-time mechanisms those two papers introduce, run over this project's
retrieval layer and driven by the same local model as every other arm. The
distinction matters and the paper states it: Self-RAG's published system depends
on a model fine-tuned to emit reflection tokens, and CRAG's depends on a
fine-tuned T5-large retrieval evaluator with per-dataset thresholds. Neither
checkpoint is used here.

Why reimplement rather than run theirs
--------------------------------------
Both published systems assume a static, pre-embedded corpus -- Self-RAG's
reference implementation retrieves with Contriever over the DPR Wikipedia split
-- whereas the questions here are answered from live release, advisory and
community endpoints. Running their checkpoints on their corpus would produce
numbers from a different retrieval distribution and a different knowledge cutoff,
which would not be comparable to anything else in this paper. Running their
*algorithms* over our retrieval, with the model held constant, isolates what the
mechanism contributes in this domain, which is the question a reader actually
has.

What is reimplemented
---------------------
From Self-RAG (Asai et al., ICLR 2024), the per-passage critique loop:

  ISREL   is this passage relevant to the question?
  ISSUP   is the drafted answer supported by the passages kept?

From CRAG (Yan et al., 2024), the corrective control flow: score retrieval,
then take one of three actions -- accept, refine by discarding the passages that
fail ISREL, or decline when nothing survives. CRAG's third branch is a web
search, which is unavailable in a fixed-corpus comparison, so declining stands
in its place. That substitution is a deviation and is recorded as one.

The abstention path is the point of the arm. CRAG-style scoring rewards
declining over guessing, and our own Evaluator expresses that only as a scalar
threshold. This baseline decides per passage instead, which is the mechanism the
literature actually proposes.

Determinism: every critique call runs at temperature 0. The critiques are
LLM judgements, so they are not deterministic across model versions, but they
are reproducible for a fixed model and prompt.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .providers import LLMClient, LLMError, make_client

# A passage must earn its place. The prompt asks for one token so the reply is
# cheap to parse and hard to hedge.
ISREL_PROMPT = (
    "You are judging whether a retrieved document is relevant to a software "
    "update question.\n\n"
    "Question: {query}\n\n"
    "Document [{source}] {title}\n{text}\n\n"
    "Is this document relevant to answering the question? A document is "
    "relevant only if it concerns the same software, product, or vendor the "
    "question is about. A document about a different product is not relevant "
    "even if it discusses updates or vulnerabilities.\n"
    "Answer with exactly one word: RELEVANT or IRRELEVANT."
)

ISSUP_PROMPT = (
    "You are judging whether an answer is supported by the sources given.\n\n"
    "Question: {query}\n\nSources:\n{ctx}\n\nProposed answer: {answer}\n\n"
    "Is every factual claim in the proposed answer -- in particular every "
    "version number, date, and identifier -- stated in or directly implied by "
    "the sources?\n"
    "Answer with exactly one word: SUPPORTED, PARTIAL, or UNSUPPORTED."
)

DECLINE_TEXT = (
    "The retrieved sources do not answer this question. No relevant "
    "release note, advisory, or community discussion was found for the "
    "software the question asks about."
)


def _one_word(reply: str) -> str:
    """First alphabetic token of a reply, uppercased. '' when there is none."""
    for tok in (reply or "").replace("*", " ").split():
        cleaned = "".join(c for c in tok if c.isalpha())
        if cleaned:
            return cleaned.upper()
    return ""


def doc_context(docs: List[dict], limit: int = 200) -> str:
    return "\n".join(
        f"- [{d.get('source','?')}] {d.get('title','')}: "
        f"{(d.get('detail') or d.get('text') or '')[:limit]}"
        for d in docs
    ) or "No documents retrieved."


class SelfReflectiveRAG:
    """The critique loop. Retrieval is injected, so the arm shares a pool with
    every other system and the comparison isolates the mechanism."""

    def __init__(self, client: LLMClient, top_k: int = 4,
                 keep_partial: bool = True):
        self.client = client
        self.top_k = top_k
        # PARTIAL support is kept by default: in this domain an answer that
        # correctly names a version while adding unsupported colour is more
        # useful than a refusal, and CRAG's scoring already penalises the
        # unsupported part. Set False for the strict reading.
        self.keep_partial = keep_partial

    # ---------------------------------------------------------------- critique

    def is_relevant(self, query: str, doc: dict) -> bool:
        prompt = ISREL_PROMPT.format(
            query=query,
            source=doc.get("source", "?"),
            title=doc.get("title", ""),
            text=(doc.get("detail") or doc.get("text") or "")[:600],
        )
        try:
            verdict = _one_word(self.client.generate(prompt, temperature=0.0,
                                                     max_tokens=8))
        except LLMError:
            # A failed critique must not silently discard a document; keeping it
            # biases toward the non-abstaining behaviour of the other arms,
            # which is the conservative direction for this arm's own claim.
            return True
        return verdict.startswith("RELEVANT")

    def support_verdict(self, query: str, docs: List[dict], answer: str) -> str:
        prompt = ISSUP_PROMPT.format(query=query, ctx=doc_context(docs),
                                     answer=answer)
        try:
            return _one_word(self.client.generate(prompt, temperature=0.0,
                                                  max_tokens=8)) or "PARTIAL"
        except LLMError:
            return "PARTIAL"

    # ------------------------------------------------------------------ answer

    def run(self, query: str, docs: List[dict], synthesis_prompt_fn) -> Dict:
        """Critique, refine, answer or decline.

        `synthesis_prompt_fn(query, docs, top_k) -> str` is passed in so this
        arm drafts with exactly the prompt the other doc-grounded arms use;
        otherwise a prompt difference would be confounded with the mechanism.
        """
        trace = {"n_retrieved": len(docs)}

        kept = [d for d in docs[: self.top_k] if self.is_relevant(query, d)]
        trace["n_relevant"] = len(kept)

        if not kept:
            trace["action"] = "decline_no_relevant"
            return {"answer": DECLINE_TEXT, "kept": [], "trace": trace}

        try:
            draft = self.client.generate(
                synthesis_prompt_fn(query, kept, self.top_k),
                temperature=0.0, max_tokens=400)
        except LLMError as e:
            trace["action"] = "generation_error"
            return {"answer": f"[generation error: {e}]", "kept": kept,
                    "trace": trace}

        verdict = self.support_verdict(query, kept, draft)
        trace["support"] = verdict

        accept = verdict.startswith("SUPPORTED") or (
            self.keep_partial and verdict.startswith("PARTIAL"))
        if accept:
            trace["action"] = "accept"
            return {"answer": draft, "kept": kept, "trace": trace}

        trace["action"] = "decline_unsupported"
        return {"answer": DECLINE_TEXT, "kept": kept, "trace": trace}
