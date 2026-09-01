"""
Tests for the Temporal Grounder.

The clock is injected in every case, so a test that passes today still passes
next August -- the failure mode these rules exist to fix is date-dependent, and
a date-dependent test cannot detect a regression in it.

Offline: the module is pure, nothing here touches the network.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from temporal import resolve_temporal, matches_window  # noqa: E402

# A Monday-anchored reference: 2026-08-31 is a Monday, which makes the
# week-boundary cases explicit rather than accidental.
NOW = date(2026, 8, 31)
assert NOW.weekday() == 0


def test_today_becomes_both_date_forms():
    r = resolve_temporal("Any critical Linux updates today?", now=NOW)
    assert r.query == "Any critical Linux updates on Aug 31, 2026 (2026-08-31)?"
    # Both forms, because BM25 matches the ISO string the feeds publish and a
    # reader matches the human one.
    assert "Aug 31, 2026" in r.query and "2026-08-31" in r.query
    assert r.window == (NOW, NOW)
    assert r.changed


def test_yesterday_and_tomorrow():
    assert "2026-08-30" in resolve_temporal("what shipped yesterday", now=NOW).query
    assert "2026-09-01" in resolve_temporal("what ships tomorrow", now=NOW).query


def test_past_n_days_becomes_a_span():
    r = resolve_temporal("Security patches in the past 7 days", now=NOW)
    assert r.window == (date(2026, 8, 24), NOW)
    assert "between Aug 24, 2026 and Aug 31, 2026" in r.query


def test_number_words_and_units():
    assert resolve_temporal("bugs fixed in the last two weeks", now=NOW).window \
        == (date(2026, 8, 17), NOW)
    assert resolve_temporal("CVEs over the past three months", now=NOW).window \
        == (date(2026, 6, 2), NOW)


def test_this_week_stops_at_today_not_at_sunday():
    # The future half of the current week holds nothing to retrieve, so
    # widening the window into it can only admit noise.
    r = resolve_temporal("releases this week", now=date(2026, 8, 26))
    assert r.window == (date(2026, 8, 24), date(2026, 8, 26))


def test_last_week_is_the_previous_full_week():
    r = resolve_temporal("MacOS bugs fixed last week", now=NOW)
    assert r.window == (date(2026, 8, 24), date(2026, 8, 30))


def test_month_and_year_boundaries():
    assert resolve_temporal("releases this month", now=NOW).window \
        == (date(2026, 8, 1), NOW)
    assert resolve_temporal("releases last month", now=NOW).window \
        == (date(2026, 7, 1), date(2026, 7, 31))
    assert resolve_temporal("anything last year?", now=NOW).window \
        == (date(2025, 1, 1), date(2025, 12, 31))


def test_version_ordinals_are_left_alone():
    # "latest" means newest release, whenever it shipped. Pinning it to today
    # would narrow the query to a date the answer probably is not on.
    for q in ["Latest Django release notes", "newest Chrome version",
              "current stable kernel"]:
        r = resolve_temporal(q, now=NOW)
        assert not r.changed, q
        assert r.query == q
        assert r.window is None


def test_preposition_is_not_doubled():
    r = resolve_temporal("updates since yesterday", now=NOW)
    assert "since on" not in r.query
    assert r.query.startswith("updates since Aug 30, 2026")


def test_multiple_expressions_union_the_window():
    r = resolve_temporal("stuff from yesterday and today", now=NOW)
    assert r.window == (date(2026, 8, 30), NOW)
    assert len(r.terms) == 2


def test_inserted_dates_are_not_rematched():
    # The replacement text contains digits and month names; a second pass over
    # it must not find a new "expression" inside what was just written.
    r = resolve_temporal("today", now=NOW)
    assert len(r.terms) == 1
    assert r.query == "on Aug 31, 2026 (2026-08-31)"


def test_zero_and_nonsense_counts_are_left_alone():
    for q in ["past 0 days", "in the last 0 weeks"]:
        assert resolve_temporal(q, now=NOW).query == q


def test_datetime_now_is_accepted():
    from datetime import datetime
    r = resolve_temporal("today", now=datetime(2026, 8, 31, 14, 30))
    assert r.window == (NOW, NOW)


def test_no_expression_leaves_query_identical():
    q = "Any security vulnerabilities in Python?"
    r = resolve_temporal(q, now=NOW)
    assert r.query == q and not r.changed and r.window is None
    assert "no relative time expression" in r.describe()


@pytest.mark.parametrize("value,expected", [
    ("2026-08-31", True),
    ("2026-08-31T04:00:00Z", True),
    ("2026-08-24", True),
    ("2026-08-23", False),
    # The release feed publishes `versionReleaseDate` as a compact string,
    # e.g. "20260828" — parsing only the dashed form reported every release
    # as undated and showed "0 of 5 in window" with the releases on screen.
    ("20260828", True),
    ("20260823", False),
    ("not-a-date", None),
    ("", None),
])
def test_matches_window(value, expected):
    r = resolve_temporal("in the past 7 days", now=NOW)
    assert matches_window(value, r) is expected


def test_matches_window_without_a_window_is_unknown_not_false():
    r = resolve_temporal("Latest Django release notes", now=NOW)
    assert matches_window("2026-08-31", r) is None


def test_stripped_removes_the_expression_for_keyword_fetch():
    # The regression this exists for: fetching on the dated phrasing alone
    # took the release endpoint from 5 results to 0.
    r = resolve_temporal("Any critical Linux updates today?", now=NOW)
    assert r.stripped == "Any critical Linux updates?"
    r2 = resolve_temporal("Security patches released in the past 7 days", now=NOW)
    assert r2.stripped == "Security patches released"


def test_stripped_drops_the_dangling_preposition():
    assert resolve_temporal("updates since yesterday", now=NOW).stripped == "updates"


def test_fetch_phrasings_are_plain_first_then_dated():
    r = resolve_temporal("Any critical Linux updates today?", now=NOW)
    assert r.fetch_phrasings == [r.stripped, r.query]


def test_fetch_phrasings_is_a_single_phrasing_when_nothing_resolved():
    q = "Latest Django release notes"
    assert resolve_temporal(q, now=NOW).fetch_phrasings == [q]
