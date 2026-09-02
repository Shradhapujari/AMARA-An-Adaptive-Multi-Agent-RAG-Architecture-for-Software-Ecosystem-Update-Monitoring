"""
Tests for the shared pre-retrieval layer.

Clock and catalog are injected in every case, so the suite is offline and
date-independent -- the same two reasons `temporal` and `vendor` inject them.

The first test is the advisor's worked example, verbatim. It is the acceptance
criterion for this layer: if it ever fails, the rewrite no longer says what was
asked for.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grounding import ground  # noqa: E402

NOW = date(2026, 9, 1)
CATALOG = ["linux", "chrome", "firefox", "python", "centos", "openssl"]


def g(question):
    return ground(question, now=NOW, catalog=CATALOG)


# ── The worked example ───────────────────────────────────────────────────

def test_advisor_worked_example():
    r = g("What is the latest Linux version?")
    assert r.rewritten == \
        "What is the latest Linux kernel version on Sep 1, 2026 (2026-09-01)?"
    assert r.vendor_names == ["linux"]
    assert r.intent.label == "release"


def test_worked_example_may_not_cite_a_cve_row():
    # The record-type repair, stated as a routing rule: a "latest version"
    # answer citing an NVD affected-version string is how v25.642087.0 happened.
    assert "cve" not in g("What is the latest Linux version?").citable_kinds


# ── As-of dating ─────────────────────────────────────────────────────────

def test_latest_gets_an_as_of_date_even_with_no_time_word():
    assert "on Sep 1, 2026 (2026-09-01)" in g("What is the newest Firefox?").rewritten


def test_as_of_date_never_reaches_the_retrieval_phrasings():
    # Pinning "latest" to a date narrows the keyword query to zero rows; the
    # date is for the reader, not for the endpoint.
    r = g("What is the latest Linux version?")
    assert all("2026-09-01" not in p for p in r.retrieval_phrasings)


def test_as_of_keeps_the_question_mark_last():
    assert g("What is the latest Firefox?").rewritten.endswith("?")


def test_question_without_a_time_reference_is_not_dated():
    # Asserted as "unchanged", not as "contains no 2026": the version string
    # v1020260105.0.0 has a 2026 inside it.
    q = "What changed in CentOS v1020260105.0.0?"
    assert g(q).rewritten == q


def test_explicit_time_word_still_wins():
    # "today" is resolved by temporal; the as-of clause must not also fire and
    # date the question twice.
    r = g("Any critical Linux updates today?")
    assert r.rewritten.count("2026-09-01") == 1


# ── Retrieval phrasings ──────────────────────────────────────────────────

def test_vendor_term_leads_the_phrasings():
    # /api/v/ matches q against product names only: "linux" -> 606 rows,
    # "linux version" -> 0. The bare product has to be fetched.
    assert g("What is the latest Linux version?").retrieval_phrasings[0] == "linux"


def test_phrasings_include_a_stopword_stripped_form():
    assert "latest Linux version" in g("What is the latest Linux version?").retrieval_phrasings


def test_phrasings_are_deduplicated():
    p = g("linux").retrieval_phrasings
    assert len(p) == len({x.lower() for x in p})


# ── Routing ──────────────────────────────────────────────────────────────

def test_thin_question_asks_for_clarification():
    # No product, no intent cue. Answering from whatever the feeds returned is
    # what produced answers that read as hallucinations.
    assert g("how do I fix this").needs_clarification


def test_grounded_question_does_not_ask_for_clarification():
    assert not g("Any CVEs in OpenSSL?").needs_clarification


def test_unrouted_question_still_searches_every_pool():
    r = g("how do I fix this")
    assert set(r.citable_kinds) == {"release", "cve", "community"}
    assert set(r.pool_weights.values()) == {1.0}


def test_opinion_question_weights_community_highest():
    w = g("Is anyone else hating the new Chrome UI?").pool_weights
    assert w["community"] == max(w.values())


# ── Trace ────────────────────────────────────────────────────────────────

def test_describe_covers_every_step():
    lines = " ".join(g("Any critical Linux updates today?").describe())
    for step in ("temporal:", "vendors:", "intent:", "terms:"):
        assert step in lines


def test_grounding_is_deterministic():
    a, b = g("Any critical Linux updates today?"), g("Any critical Linux updates today?")
    assert a.rewritten == b.rewritten
    assert a.retrieval_phrasings == b.retrieval_phrasings


# ── retrieval_query vs retrieval_phrasings ───────────────────────────────
#
# Two accessors because two consumers need opposite things. `/api/v/` matches
# `q` against product names only -- "linux" returns 606 rows, "linux version"
# returns 0 -- so `retrieval_phrasings` leads with the bare product. A general
# keyword retriever scoring over mixed text needs the token that *narrows*,
# which the product name never is. Benchmark question 29 measured the cost of
# conflating them: retrieving "Is Mozilla Firefox v148.0.0 the latest release?"
# as "firefox" scored recall@5 0.00 where the raw question scored 1.00.

def test_retrieval_query_keeps_the_version_that_identifies_the_answer():
    g = ground("Is Mozilla Firefox v148.0.0 the latest release, or is there a newer one?")
    assert "v148.0.0" in g.retrieval_query
    assert "firefox" in g.retrieval_query.lower()


def test_retrieval_phrasings_still_lead_with_the_bare_product():
    # The endpoint-facing accessor must not inherit the change.
    g = ground("Is Mozilla Firefox v148.0.0 the latest release, or is there a newer one?")
    assert g.retrieval_phrasings[0] == "firefox"
    assert g.retrieval_phrasings[0] != g.retrieval_query


def test_retrieval_query_drops_stopwords():
    g = ground("Is Mozilla Firefox v148.0.0 the latest release, or is there a newer one?")
    for stop in (" is ", " the ", " or ", " there "):
        assert stop not in f" {g.retrieval_query.lower()} "


def test_retrieval_query_keeps_a_build_number():
    g = ground("When was Google Chrome v145.0.7611 released and on which channel?")
    assert "v145.0.7611" in g.retrieval_query


def test_retrieval_query_survives_an_unknown_product():
    # No catalog match: still a usable keyword query, not an empty string.
    g = ground("Does Frobnicator v3.2.1 ship a dark mode?")
    assert g.retrieval_query.strip()
    assert "v3.2.1" in g.retrieval_query


def test_retrieval_query_is_bounded():
    g = ground("What are all of the many different changes and fixes and features "
               "and improvements shipped in the newest Linux kernel release?")
    assert len(g.retrieval_query.split()) <= 6
