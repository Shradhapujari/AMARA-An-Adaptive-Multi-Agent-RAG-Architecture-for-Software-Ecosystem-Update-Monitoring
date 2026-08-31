"""
Tests for corpus_snapshot.py — the frozen-corpus control.

The rerank ablation of 2026-08-30 could not be interpreted because the sources
moved between arms: the same question and the same system returned a different
document set on 10 of 10 questions across consecutive runs. These tests pin the
property that fixes it — replay must return the recorded bytes and must not
touch the network — plus the honesty properties around it: a miss is counted
and attributed, and a run that read a document host live is not reported as
frozen.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import corpus_snapshot  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────

class FakeResponse:
    """Minimal stand-in for what requests.get returns.

    Record mode hands the caller the real response object through untouched, so
    this needs the same surface the project uses off a live one.
    """

    def __init__(self, status, content, headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content.decode("utf-8", "replace"))


class FakeUrlResponse:
    def __init__(self, status, content):
        self.status = status
        self._c = content
        self.headers = {}

    def read(self):
        return self._c

    def getcode(self):
        return self.status

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _snap(tmp_path, mode):
    return corpus_snapshot.Snapshot(mode, str(tmp_path / "snap"))


# ── keying ───────────────────────────────────────────────────────────────

def test_param_order_does_not_change_the_key():
    """?a=1&b=2 and ?b=2&a=1 are the same request and must share a recording."""
    a = corpus_snapshot.request_key("GET", "https://x.io/api", {"a": 1, "b": 2})
    b = corpus_snapshot.request_key("GET", "https://x.io/api", {"b": 2, "a": 1})
    assert a == b


def test_params_in_the_url_and_in_the_dict_are_equivalent():
    a = corpus_snapshot.request_key("GET", "https://x.io/api?q=firefox")
    b = corpus_snapshot.request_key("GET", "https://x.io/api", {"q": "firefox"})
    assert a == b


def test_different_params_are_different_keys():
    a = corpus_snapshot.request_key("GET", "https://x.io/api", {"q": "firefox"})
    b = corpus_snapshot.request_key("GET", "https://x.io/api", {"q": "chrome"})
    assert a != b


def test_body_participates_in_the_key():
    """Two Ollama prompts to one endpoint are two different requests."""
    a = corpus_snapshot.request_key("POST", "http://localhost:11434/api/generate",
                                    None, b'{"prompt":"a"}')
    b = corpus_snapshot.request_key("POST", "http://localhost:11434/api/generate",
                                    None, b'{"prompt":"b"}')
    assert a != b


# ── record then replay ───────────────────────────────────────────────────

def test_replay_returns_recorded_bytes_without_calling_the_network(tmp_path, monkeypatch):
    import requests

    calls = {"n": 0}

    def fake_get(url, **kw):
        calls["n"] += 1
        return FakeResponse(200, json.dumps({"data": ["rec-1"]}).encode())

    monkeypatch.setattr(requests, "get", fake_get)
    with _snap(tmp_path, "record"):
        first = requests.get("https://releasetrain.io/api/v/", params={"q": "firefox"})
    assert first.json() == {"data": ["rec-1"]}
    assert calls["n"] == 1

    # The live endpoint now answers differently — replay must not notice.
    def moved_on(url, **kw):
        calls["n"] += 1
        return FakeResponse(200, json.dumps({"data": ["rec-2-DIFFERENT"]}).encode())

    monkeypatch.setattr(requests, "get", moved_on)
    snap = _snap(tmp_path, "replay")
    with snap:
        second = requests.get("https://releasetrain.io/api/v/", params={"q": "firefox"})
    assert second.json() == {"data": ["rec-1"]}, "replay served live data"
    assert calls["n"] == 1, "replay hit the network"
    assert snap.stats()["hits"] == 1


def test_replay_of_urlopen_serves_recorded_bytes(tmp_path, monkeypatch):
    """call_llama and the embedding reranker both go through urlopen."""
    def fake_urlopen(req, *a, **kw):
        return FakeUrlResponse(200, json.dumps({"response": "rewritten once"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                 data=b'{"prompt":"p"}', method="POST")
    with _snap(tmp_path, "record"):
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read())["response"] == "rewritten once"

    def drifted(req, *a, **kw):
        return FakeUrlResponse(200, json.dumps({"response": "DIFFERENT"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", drifted)
    with _snap(tmp_path, "replay"):
        req2 = urllib.request.Request("http://localhost:11434/api/generate",
                                      data=b'{"prompt":"p"}', method="POST")
        with urllib.request.urlopen(req2) as r:
            assert json.loads(r.read())["response"] == "rewritten once"


def test_stop_restores_the_original_functions(tmp_path, monkeypatch):
    import requests

    original = requests.get
    original_urlopen = urllib.request.urlopen
    snap = _snap(tmp_path, "record")
    snap.start()
    assert requests.get is not original
    snap.stop()
    assert requests.get is original
    assert urllib.request.urlopen is original_urlopen


# ── miss accounting ──────────────────────────────────────────────────────

def test_a_replay_miss_goes_live_and_is_counted(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get",
                        lambda url, **kw: FakeResponse(200, b'{"data":[]}'))
    snap = _snap(tmp_path, "replay")
    with snap:
        requests.get("https://releasetrain.io/api/v/", params={"q": "never-recorded"})
    st = snap.stats()
    assert st["misses"] == 1
    assert st["misses_by_host"] == {"releasetrain.io": 1}


def test_a_corpus_host_miss_means_the_run_is_not_frozen(tmp_path, monkeypatch):
    """The whole point of the flag: a document read live voids the comparison."""
    import requests

    monkeypatch.setattr(requests, "get",
                        lambda url, **kw: FakeResponse(200, b"{}"))
    snap = _snap(tmp_path, "replay")
    with snap:
        requests.get("https://releasetrain.io/api/v/")
    st = snap.stats()
    assert st["corpus_misses"] == 1
    assert st["frozen"] is False


def test_a_model_host_miss_does_not_void_the_run(tmp_path, monkeypatch):
    """The embed arm calls Ollama endpoints the `none` arm never recorded."""
    def fake_urlopen(req, *a, **kw):
        return FakeUrlResponse(200, b'{"embedding":[0.1,0.2]}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    snap = _snap(tmp_path, "replay")
    with snap:
        r = urllib.request.Request("http://localhost:11434/api/embeddings",
                                   data=b'{"prompt":"x"}', method="POST")
        urllib.request.urlopen(r)
    st = snap.stats()
    assert st["misses"] == 1
    assert st["corpus_misses"] == 0
    assert st["frozen"] is True


def test_a_miss_is_recorded_so_the_next_arm_hits(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get",
                        lambda url, **kw: FakeResponse(200, b'{"data":["x"]}'))
    with _snap(tmp_path, "replay"):
        requests.get("https://releasetrain.io/api/v/")

    monkeypatch.setattr(requests, "get",
                        lambda url, **kw: FakeResponse(200, b'{"data":["CHANGED"]}'))
    snap2 = _snap(tmp_path, "replay")
    with snap2:
        r = requests.get("https://releasetrain.io/api/v/")
    assert r.json() == {"data": ["x"]}
    assert snap2.stats()["misses"] == 0


# ── host classification ──────────────────────────────────────────────────

def test_document_hosts_are_recognised():
    assert corpus_snapshot.is_corpus_host("https://releasetrain.io/api/v/")
    assert corpus_snapshot.is_corpus_host("https://www.reddit.com/r/Ubiquiti.json")
    assert corpus_snapshot.is_corpus_host("https://www.cisa.gov/kev.json")


def test_the_local_model_server_is_not_a_document_host():
    assert not corpus_snapshot.is_corpus_host("http://localhost:11434/api/generate")


# ── activation ───────────────────────────────────────────────────────────

def test_no_spec_means_live_and_no_patching():
    assert corpus_snapshot.activate("") is None


def test_a_spec_without_a_directory_fails_loudly():
    """A typo must not silently degrade an ablation to a live run."""
    try:
        corpus_snapshot.activate("replay")
    except ValueError as e:
        assert "record:<dir>" in str(e)
    else:
        raise AssertionError("expected ValueError for a spec with no directory")


def test_an_unknown_mode_fails_loudly(tmp_path):
    try:
        corpus_snapshot.Snapshot("reply", str(tmp_path))
    except ValueError as e:
        assert "record|replay" in str(e)
    else:
        raise AssertionError("expected ValueError for an unknown mode")
