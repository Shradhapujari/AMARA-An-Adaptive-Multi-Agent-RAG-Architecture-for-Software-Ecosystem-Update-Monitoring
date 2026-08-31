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

One bound holds throughout and is load-bearing for the threats discussion: **a
document is discarded only on an explicit IRRELEVANT verdict.** Backend errors,
empty completions, hedged replies and preambles that crowd out the verdict all
keep the document. The critic shares a model with the judge that later labels
relevance for scoring, so discarding is the direction that narrows the candidate
set toward the judge's own preferences; failing closed would deepen that
circularity in proportion to how often the critique is malformed, and invisibly.

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


def find_verdict(reply: str, options) -> str:
    """The verdict a reply states, or '' if it states none.

    Three properties, each earned by a reply shape observed or reasoned about:

    * **Position-independent.** A first-token parse is defeated by anything the
      model puts in front of the verdict -- "Sure! RELEVANT" parses to SURE --
      and at a small token budget a preamble costs the whole verdict. The reply
      only has to contain the judgement.

    * **Whole-word.** Matching is on word boundaries, not substrings, so
      RELEVANT cannot be found inside IRRELEVANT. Substring matching made the
      option order load-bearing: test RELEVANT first and every rejection reads
      as an approval, which disables the filter silently. The order below is
      still longest-first as defence in depth, but correctness no longer rests
      on it.

    * **Negation-aware.** "not irrelevant" contains IRRELEVANT and means the
      opposite. A negated verdict is skipped rather than honoured, so such a
      reply falls through to the caller's default instead of being read
      backwards. This is the direction that matters: for the relevance critique,
      reading a negated rejection as a rejection would discard a document the
      critic wanted to keep, and discarding is what narrows the candidate set
      toward the critic's own preferences.

    Returns the first option that appears as a non-negated word.
    """
    words = [
        "".join(c for c in tok if c.isalpha()).upper()
        for tok in (reply or "").replace("*", " ").replace("/", " ").split()
    ]
    words = [w for w in words if w]
    negators = {"NOT", "ISNT", "ISN", "NEITHER", "NEVER", "NO"}
    for opt in options:
        for i, w in enumerate(words):
            if w != opt:
                continue
            if i and words[i - 1] in negators:
                continue  # negated: this reply does not assert `opt`
            return opt
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
            reply = self.client.generate(prompt, temperature=0.0, max_tokens=16)
        except LLMError:
            # A failed critique must not silently discard a document; keeping it
            # biases toward the non-abstaining behaviour of the other arms,
            # which is the conservative direction for this arm's own claim.
            return True
        # IRRELEVANT must be tested before RELEVANT: the latter is a substring of
        # the former, so the reverse order reads every rejection as an approval.
        verdict = find_verdict(reply, ("IRRELEVANT", "RELEVANT"))
        # Drop only on an explicit rejection. An empty completion, a hedge
        # ("MAYBE"), a refusal, or a preamble that crowds the verdict out of the
        # token budget all keep the document. This is the same direction as the
        # LLMError path and for the same reason: dropping is what narrows the
        # candidate set toward the critic's own preferences, and the critic here
        # shares a model with the judge that later scores relevance. Failing
        # closed would make that circularity worse, silently, in proportion to
        # how often the critique is malformed.
        return verdict != "IRRELEVANT"

    def support_verdict(self, query: str, docs: List[dict], answer: str) -> str:
        prompt = ISSUP_PROMPT.format(query=query, ctx=doc_context(docs),
                                     answer=answer)
        try:
            reply = self.client.generate(prompt, temperature=0.0, max_tokens=16)
        except LLMError:
            return "PARTIAL"
        # UNSUPPORTED before SUPPORTED, for the substring reason above.
        return find_verdict(reply, ("UNSUPPORTED", "SUPPORTED", "PARTIAL")) or "PARTIAL"

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
