"""
Stopword removal for the retrieval phrasing.
============================================
`/api/v/` and the Reddit query endpoints match `q` as text. A question asked in
English carries most of its length in words that cannot discriminate between
documents -- "what", "is", "the", "any", "in" -- and every one of them is a
term the endpoint tries to match. Measured against the live endpoint on
2026-09-01:

    q="What is the latest Linux version?"   ->   0 rows
    q="latest linux version"                ->   0 rows
    q="linux"                               -> 606 rows

so the failure is not gradual. A sentence retrieves nothing; the content terms
retrieve everything there is. This module is the step between the two.

It is deliberately separate from `fetch_union._STOPWORDS`, which serves a
different purpose (guarding the capitalisation heuristic that guesses product
names) and whose exact membership is baked into published retrieval numbers.
Changing that set would silently move results reported in the paper, so it is
left alone and this one is additive.

Ordering is preserved rather than sorted: the endpoints weight earlier terms
more heavily, and the user's own word order is the best available signal for
what the question is mostly about.
"""

from __future__ import annotations

import re
from typing import List, Sequence

__all__ = [
    "QUESTION_STOPWORDS",
    "content_terms",
    "strip_stopwords",
    "keyword_query",
]

# Function words and question scaffolding. Domain words ("security", "update",
# "release") are deliberately NOT here: they are stopwords for *product
# detection*, where they cause false vendor matches, but they are real content
# for retrieval -- "security update" is a meaningfully narrower query than
# "linux". `fetch_union._STOPWORDS` covers the other use.
QUESTION_STOPWORDS = frozenset("""
a about above after again against all also am an and any are aren't as at
be because been before being below between both but by
can can't cannot could couldn't
did didn't do does doesn't doing don't down during
each
few for from further
had hadn't has hasn't have haven't having he her here hers herself him himself
his how how's
i i'd i'll i'm i've if in into is isn't it it's its itself
just
let's
me more most mustn't my myself
no nor not
of off on once only or other ought our ours ourselves out over own
please
same shan't she should shouldn't so some such
than that that's the their theirs them themselves then there there's these they
this those through to too
under until up
very
was wasn't we were weren't what what's when when's where where's which while
who who's whom why why's will with won't would wouldn't
you your yours yourself yourselves
""".split())


def content_terms(query: str, keep: Sequence[str] = ()) -> List[str]:
    """The query's content words, in the order they were written.

    `keep` is forced through whatever the stopword list says -- callers pass
    detected product names, so a product that happens to be spelled like a
    function word ("Go", "R", "Next") survives.
    """
    forced = {k.lower() for k in keep}
    out: List[str] = []
    for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+#_-]*", query):
        low = word.lower().strip(".")
        if not low:
            continue
        if low in forced or low not in QUESTION_STOPWORDS:
            if low not in [o.lower() for o in out]:
                out.append(word)
    return out


def strip_stopwords(query: str, keep: Sequence[str] = ()) -> str:
    """`query` with its function words removed, still readable as a phrase."""
    return " ".join(content_terms(query, keep))


def keyword_query(query: str, vendors: Sequence[str] = (), limit: int = 6) -> str:
    """The phrasing to send to a keyword endpoint.

    Products first -- they are what `/api/v/` actually matches on -- then the
    remaining content words up to `limit`, which keeps the query short enough
    that the endpoint's own AND-ing does not drive it to zero rows.
    """
    terms: List[str] = []
    for v in vendors:
        if v and v.lower() not in [t.lower() for t in terms]:
            terms.append(v)
    for t in content_terms(query, keep=vendors):
        if t.lower() not in [x.lower() for x in terms]:
            terms.append(t)
    return " ".join(terms[:limit])
