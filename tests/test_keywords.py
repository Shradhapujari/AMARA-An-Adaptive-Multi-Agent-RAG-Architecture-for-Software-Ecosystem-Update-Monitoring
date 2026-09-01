"""
Tests for stopword removal on the retrieval phrasing.

The numbers in the module docstring were measured against the live endpoint;
these tests pin the behaviour that produces them without needing the network.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from keywords import (  # noqa: E402
    QUESTION_STOPWORDS,
    content_terms,
    keyword_query,
    strip_stopwords,
)


def test_function_words_are_removed():
    assert content_terms("What is the latest Linux version?") == \
        ["latest", "Linux", "version"]


def test_word_order_is_preserved():
    # The endpoints weight earlier terms more heavily, so sorting would throw
    # away the user's own signal about what the question is mostly about.
    assert content_terms("Chrome security patch") == ["Chrome", "security", "patch"]


def test_domain_words_are_kept():
    # "security update" is a meaningfully narrower query than "linux"; these
    # are stopwords for product detection, not for retrieval.
    terms = [t.lower() for t in content_terms("any security update for linux")]
    assert "security" in terms and "update" in terms


def test_duplicates_collapse():
    assert content_terms("linux Linux LINUX") == ["linux"]


def test_versions_survive():
    assert "v6.18.21" in content_terms("What changed in v6.18.21?")


def test_kept_terms_override_the_stopword_list():
    # "Go" and "Next" are products whose names are ordinary function words.
    assert "Go" in content_terms("How is Go doing?", keep=["go"])


def test_strip_stopwords_returns_a_readable_phrase():
    assert strip_stopwords("What is the latest Linux version?") == "latest Linux version"


def test_keyword_query_puts_the_product_first():
    # /api/v/ matches q against product names, so the product has to lead.
    q = keyword_query("What is the latest Linux version?", vendors=["linux"])
    assert q.split()[0] == "linux"


def test_keyword_query_does_not_repeat_the_product():
    q = keyword_query("latest linux version", vendors=["linux"]).lower().split()
    assert q.count("linux") == 1


def test_keyword_query_is_bounded():
    long_q = "what is the newest stable security patched release version of the linux kernel today"
    assert len(keyword_query(long_q, vendors=["linux"], limit=4).split()) <= 4


def test_stopword_list_holds_the_words_the_advisor_named():
    assert {"is", "the", "a", "an", "what", "when"} <= QUESTION_STOPWORDS
