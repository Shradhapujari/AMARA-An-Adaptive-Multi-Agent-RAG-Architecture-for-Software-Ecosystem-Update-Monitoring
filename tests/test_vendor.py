"""
Tests for vendor grounding: catalog, detection, record type, filtering.

The catalog is injected in every case rather than downloaded, so the suite is
offline and a test that passes today still passes when upstream adds a product.
The record-type cases carry real rows from `/api/v/?q=Linux` (2026-09-01),
because the bug they pin is a property of the live data and a synthetic row
would not have caught it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vendor import (  # noqa: E402
    VendorMatch,
    classify_record,
    detect_vendors,
    disambiguate,
    filter_by_vendor,
    filter_community,
    is_release_record,
    load_catalog,
    subreddit_vendor,
    vendor_terms,
)

CATALOG = ["linux", "chrome", "firefox", "python", "visual studio code",
           "code", "chromium-bsu", "linuxcnc", "go", "node.js", "openssl"]


# ── Detection ────────────────────────────────────────────────────────────

def test_detects_a_catalog_product():
    assert [v.name for v in detect_vendors("latest Chrome release", CATALOG)] == ["chrome"]


def test_longest_name_wins_over_its_substring():
    # "visual studio code" contains "code", which is also a catalog entry. The
    # shorter name must not also fire, or the question retrieves two products.
    names = [v.name for v in detect_vendors("Visual Studio Code update", CATALOG)]
    assert names == ["visual studio code"]


def test_alias_resolves_to_the_catalog_spelling():
    v = detect_vendors("latest kernel version", CATALOG)[0]
    assert (v.name, v.matched, v.via_alias) == ("linux", "kernel", True)


def test_substring_of_another_product_is_not_a_match():
    # chromium-bsu is a game. A Chrome question must not retrieve it, and this
    # is the case the old capitalisation heuristic got wrong.
    assert [v.name for v in detect_vendors("chromium-bsu crash", CATALOG)] == ["chromium-bsu"]


def test_no_product_named_is_no_match():
    assert detect_vendors("What are the 3 latest updates?", CATALOG) == []


def test_numeric_and_stopword_catalog_entries_are_never_matchable():
    # /api/c/names really contains "3", "4.20", "the" and "latest"; matching
    # them turns ordinary question words into product filters.
    junk = load_catalog(path="/nonexistent-catalog.json", fetch=False)
    assert "3" not in junk and "latest" not in junk and "version" not in junk


def test_catalog_falls_back_when_no_cache_and_no_network():
    names = load_catalog(path="/nonexistent-catalog.json", fetch=False)
    assert "linux" in names and "chrome" in names


def test_vendor_terms_are_the_fetch_phrasings():
    vs = detect_vendors("Chrome and Firefox updates", CATALOG)
    assert set(vendor_terms(vs)) == {"chrome", "firefox"}


# ── Disambiguation ───────────────────────────────────────────────────────

def test_linux_is_disambiguated_to_the_kernel():
    q = "What is the latest Linux version?"
    vs = detect_vendors(q, CATALOG)
    assert disambiguate(q, vs) == "What is the latest Linux kernel version?"


def test_disambiguation_is_idempotent():
    q = "What is the latest Linux kernel version?"
    vs = detect_vendors(q, CATALOG)
    assert disambiguate(q, vs) == q


def test_unambiguous_product_is_left_alone():
    q = "Any Python security fixes?"
    assert disambiguate(q, detect_vendors(q, CATALOG)) == q


# ── Record type ──────────────────────────────────────────────────────────
# Real rows, verbatim from /api/v/?q=Linux on 2026-09-01.

ADVISORY = {"product": "Linux", "version": "25.642087.0", "date": "20260828",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-80688",
            "isCve": True,
            "notes": "In the Linux kernel, the following vulnerability has been resolved:"}

RELEASE = {"product": "linux", "version": "7.1.0", "date": "20260719",
           "url": "https://github.com/torvalds/linux", "isCve": False,
           "notes": "Linux 7.2-rc4"}


def test_cve_row_is_an_advisory_not_a_release():
    # The bug this whole module exists for: 25.642087.0 is an NVD
    # affected-version string, and answering "latest version" with it is wrong.
    assert classify_record(ADVISORY) == "advisory"
    assert not is_release_record(ADVISORY)


def test_shipped_version_is_a_release():
    assert classify_record(RELEASE) == "release"
    assert is_release_record(RELEASE)


def test_nvd_url_alone_marks_an_advisory_when_the_flag_is_missing():
    row = dict(ADVISORY)
    del row["isCve"]
    assert classify_record(row) == "advisory"


def test_latest_release_is_chosen_over_a_newer_advisory():
    # The advisory is 40 days newer. Sorting by date without classifying first
    # is exactly how the demo answered with 25.642087.0.
    rows = [ADVISORY, RELEASE]
    releases = [r for r in rows if is_release_record(r)]
    assert [r["version"] for r in releases] == ["7.1.0"]


# ── Vendor filtering ─────────────────────────────────────────────────────

def test_filter_keeps_only_the_named_product():
    rows = [{"product": "linux"}, {"product": "LinuxCNC"}, {"product": "chrome"}]
    kept = filter_by_vendor(rows, [VendorMatch("linux", "linux")])
    assert kept == [{"product": "linux"}]


def test_filter_is_exact_not_substring():
    rows = [{"product": "chromium-bsu"}]
    assert filter_by_vendor(rows, [VendorMatch("chrome", "chrome")]) == []


def test_rows_without_a_product_survive():
    # Community posts carry no product; dropping them would empty the pool.
    rows = [{"title": "a post"}]
    assert filter_by_vendor(rows, [VendorMatch("linux", "linux")]) == rows


def test_no_vendor_detected_filters_nothing():
    rows = [{"product": "linux"}, {"product": "chrome"}]
    assert filter_by_vendor(rows, []) == rows


# ── Community filtering ──────────────────────────────────────────────────

COMMUNITY = [
    {"title": "Chrome crashes on launch", "subreddit": "chrome"},
    {"title": "Edge borders are back", "subreddit": "MicrosoftEdge"},
    {"title": "How to limit battery charge?", "subreddit": "linuxquestions"},
    {"title": "Anyone else?", "subreddit": "sysadmin"},
]


def test_community_filtered_by_subreddit():
    kept = filter_community(COMMUNITY, [VendorMatch("chrome", "chrome")])
    assert [r["subreddit"] for r in kept] == ["chrome"]


def test_general_forum_is_not_attributed_to_a_product():
    # r/sysadmin discusses everything; counting it as Linux evidence would
    # attribute an unrelated complaint to whatever was asked about.
    assert subreddit_vendor("sysadmin") == ""
    kept = filter_community(COMMUNITY, [VendorMatch("linux", "linux")])
    assert all(r["subreddit"] != "sysadmin" for r in kept)


def test_product_named_in_a_title_counts_even_off_topic_subreddit():
    rows = [{"title": "Chrome broke my setup", "subreddit": "sysadmin"}]
    assert filter_community(rows, [VendorMatch("chrome", "chrome")]) == rows


def test_community_falls_back_rather_than_returning_nothing():
    # No vendor, and no content term matches: a loose pool beats an empty one.
    assert filter_community(COMMUNITY, [], terms=["kubernetes"]) == COMMUNITY
