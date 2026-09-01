"""
Regression test for the truncate-then-rank bug in fetch_vendor_releases.

`fetch_vendor_releases` has a `canonical_score` sort whose stated job is to
demote CVE rows and promote the canonical brand -- its own comment says it
"fixes Linux returning openCryptoki instead of torvalds kernel". The sort was
dead in practice, because the list was cut to `limit` *before* it ran:

    releases = releases[:limit]      # 10 rows, all advisories
    ...
    releases.sort(key=canonical_score)   # nothing left to promote

`/api/c/name/linux` returns its 449 CVE rows ahead of its 157 torvalds release
rows (advisories are filed daily, kernels are not), so the first ten were
always advisories and the shipped kernel was unreachable: measured 2026-09-01,
0 shipped releases in 40 retrieved documents.

The upstream response is stubbed here so the ordering is tested without the
network and without depending on how many advisories upstream happens to hold
today.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _StubResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _payload(n_advisories=20, n_releases=5):
    """Upstream's shape: advisories first, releases after — the real ordering."""
    rows = [{
        "versionProductName": "Linux",
        "versionProductBrand": "Linux",
        "versionNumber": f"{i}.999999.0",
        "versionReleaseDate": "20260828",
        "versionReleaseNotes": "In the Linux kernel, a vulnerability has been resolved",
        "versionUrl": f"https://nvd.nist.gov/vuln/detail/CVE-2026-{80000 + i}",
        "isCve": True,
    } for i in range(n_advisories)]
    rows += [{
        "versionProductName": "linux",
        "versionProductBrand": "torvalds",
        "versionNumber": "7.1.0",
        "versionReleaseDate": f"2026071{i}",
        "versionReleaseNotes": "Linux 7.2-rc4",
        "versionUrl": "https://github.com/torvalds/linux",
        "isCve": False,
    } for i in range(n_releases)]
    return {"linux": rows}


@pytest.fixture
def marag(monkeypatch):
    import multiagent_rag_v3 as m

    class _Stub:
        @staticmethod
        def get(url, timeout=None):
            return _StubResponse(_payload())

    monkeypatch.setattr(m, "requests", _Stub)
    return m


def test_shipped_release_survives_the_limit(marag):
    # The whole bug: with 20 advisories ahead of them, a limit of 10 used to
    # return ten advisories and zero releases.
    out = marag.fetch_vendor_releases("linux", limit=10)
    assert any("torvalds" in str(d.get("title", "")) for d in out)


def test_canonical_brand_is_ranked_first(marag):
    out = marag.fetch_vendor_releases("linux", limit=10)
    assert "torvalds" in str(out[0].get("title", ""))


def test_advisories_are_demoted_not_dropped(marag):
    # canonical_score gives CVE rows the lowest priority; it does not remove
    # them. A security question still needs them.
    out = marag.fetch_vendor_releases("linux", limit=25)
    assert any("nvd.nist.gov" in str(d.get("url", "")) for d in out)


def test_limit_is_still_honoured(marag):
    assert len(marag.fetch_vendor_releases("linux", limit=3)) == 3


def test_ranking_happens_before_the_cut(marag):
    # Ranking after cutting would put no release in a 3-row result, since the
    # first 3 upstream rows are all advisories.
    out = marag.fetch_vendor_releases("linux", limit=3)
    assert all("torvalds" in str(d.get("title", "")) for d in out)
