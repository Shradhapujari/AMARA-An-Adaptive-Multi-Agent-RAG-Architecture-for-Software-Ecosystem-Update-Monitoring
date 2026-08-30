"""
Tests for the CRAG-style scoring in eval_harness/benchmarks.py.

This module is the project's *independent* correctness signal — the one that is
supposed to be reproducible and free of an LLM judge. Its matching rules
therefore decide reported accuracy and hallucination rate directly, so each
rule needs a test that pins it, and in particular the fuzzy full-sentence match
(`_key_facts_match`) needs adversarial cases proving it cannot be talked into
scoring a wrong version or a wrong date as correct.

The `min_recall` threshold is a tunable heuristic. These tests fix the
behaviour at the shipped default so a change to it has to be deliberate.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness import benchmarks as B  # noqa: E402


# --------------------------------------------------------------- abstention

def test_strong_marker_is_an_abstention():
    assert B.is_abstention("I don't know which version shipped.") is True


def test_weak_marker_alone_is_an_abstention_only_in_the_permissive_mode():
    pred = "The severity is unknown."
    assert B.is_abstention(pred) is True
    assert B.is_abstention(pred, strong_only=True) is False


def test_marker_matching_is_word_bounded_not_substring():
    """'well-known' and 'unknowns' must not trip the 'unknown' marker."""
    assert B.is_abstention("This is a well-known regression.") is False
    assert B.is_abstention("There are several unknowns here.") is False


def test_empty_prediction_is_not_an_abstention_it_is_missing():
    # Emptiness is handled by score_prediction, not by the marker check.
    assert B.is_abstention("") is False
    assert B.score_prediction("", "Firefox 149.0.1") == "missing"


def test_hedge_inside_a_correct_answer_does_not_deflate_it():
    """The regression the strong/weak split exists to prevent."""
    pred = "The severity is unknown, but Firefox 149.0.1 is the latest release."
    assert B.score_prediction(pred, "Firefox 149.0.1") == "correct"


# ----------------------------------------------------------------- versions

def test_extract_versions_normalizes_underscore_form():
    assert "7.0.0" in B.extract_versions("Linux v7_0_0")


def test_multipart_only_rejects_bare_integers():
    assert B.extract_versions("released in 2026", multipart_only=True) == []
    assert "6.18.21" in B.extract_versions("Linux v6.18.21", multipart_only=True)


def test_wrong_version_is_incorrect_not_correct():
    assert B.score_prediction("Firefox 148.0.1 is the latest.",
                              "Firefox 149.0.1 is the latest.") == "incorrect"


def test_right_product_wrong_version_survives_the_fuzzy_path():
    """The fuzzy match must not rescue a prediction that names the wrong version.

    Almost every content word here matches the gold answer; only the version
    differs. If `_key_facts_match` ever scored this `correct`, reported accuracy
    would stop meaning anything in a domain where the version *is* the answer.
    """
    gold = "Ubuntu 26.102.0 was published on 2026-06-26 on the minor channel"
    pred = "Ubuntu 26.101.0 shipped on 2026-06-26 on the minor release channel"
    assert B.score_prediction(pred, gold) == "incorrect"


# -------------------------------------------------------------------- dates

def test_extract_dates_finds_iso_dates():
    assert B.extract_dates("published on 2026-06-26 upstream") == ["2026-06-26"]


def test_date_surface_forms_cover_common_spellings():
    forms = B.date_surface_forms("2026-06-26")
    assert B.normalize_answer("June 26 2026") in forms
    assert B.normalize_answer("20260626") in forms


def test_date_paraphrase_is_accepted():
    gold = "Ubuntu 26.102.0 was published on 2026-06-26 on the minor channel"
    pred = "Ubuntu 26.102.0 shipped June 26, 2026 on the minor release channel"
    assert B.score_prediction(pred, gold) == "correct"


def test_wrong_date_is_incorrect_even_when_the_version_matches():
    gold = "Ubuntu 26.102.0 was published on 2026-06-26 on the minor channel"
    pred = "Ubuntu 26.102.0 was published on 2026-07-14 on the minor channel"
    assert B.score_prediction(pred, gold) == "incorrect"


def test_malformed_iso_date_degrades_instead_of_raising():
    assert B.date_surface_forms("2026-13-99")  # month 13 -> falls back, no crash


# ------------------------------------------------------------ fuzzy matching

def test_paraphrase_of_the_gold_sentence_is_correct():
    gold = "Ubuntu 26.102.0 was published on 2026-06-26 on the minor channel"
    pred = "Ubuntu 26.102.0 shipped on 2026-06-26 on the minor release channel"
    assert B.score_prediction(pred, gold) == "correct"


def test_content_tokens_drop_the_paraphrase_axis_but_keep_the_facts():
    toks = B.content_tokens("Ubuntu 26.102.0 was published on 2026-06-26")
    assert "published" not in toks and "was" not in toks
    assert "ubuntu" in toks


def test_content_tokens_strip_the_v_prefix_so_versions_agree():
    assert B.content_tokens("v7.0.0") == B.content_tokens("7.0.0")


def test_unrelated_answer_carrying_the_right_version_is_not_correct():
    """Version agreement is necessary, not sufficient — token recall still gates."""
    gold = "Ubuntu 26.102.0 was published on 2026-06-26 on the minor channel"
    pred = "26.102.0"
    assert B.score_prediction(pred, gold) == "incorrect"


def test_min_recall_threshold_is_honoured():
    gold = "Ubuntu server kernel graphics networking storage regression"
    # Covers only part of the gold's content tokens.
    pred = "Ubuntu kernel"
    assert B.score_prediction(pred, gold, min_recall=0.9) == "incorrect"
    assert B.score_prediction(pred, gold, min_recall=0.2) == "correct"


# -------------------------------------------------------------- score labels

def test_missing_when_ground_truth_absent():
    assert B.score_prediction("anything", None) == "missing"
    assert B.score_prediction("anything", "   ") == "missing"


def test_list_ground_truth_accepts_any_alternative():
    assert B.score_prediction("Firefox 149.0.1",
                              ["Firefox 149.0.1", "FF 149.0.1"]) == "correct"


def test_confident_wrong_answer_is_incorrect_and_hedged_wrong_answer_is_missing():
    """The distinction crag_score exists to reward."""
    gold = "Firefox 149.0.1"
    assert B.score_prediction("Firefox 12.0 is the latest.", gold) == "incorrect"
    assert B.score_prediction("No matching source was retrieved.", gold) == "missing"


def test_back_compat_flat_marker_tuple_still_exported():
    assert "unknown" in B.ABSTENTION_MARKERS
    assert "i don't know" in B.ABSTENTION_MARKERS
