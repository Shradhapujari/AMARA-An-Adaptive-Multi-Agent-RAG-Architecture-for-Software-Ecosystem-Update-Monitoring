"""Offline tests for the LLM / AI-model source added to the retrieval layer.

These tests use fixture documents shaped like real releasetrain.io /api/v/
entries, so they run without network access.

    python -m pytest tests/test_llm_source.py -q
"""
import importlib.util
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("mrag", _ROOT / "multiagent_rag_v3.py")
mrag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mrag)


def _entry(name, ptype=None, tags=None, search=None):
    return {
        "versionProductName": name,
        "versionProductType": ptype,
        "versionReleaseTags": tags or [],
        "versionSearchTags": search or [],
    }


class TestIsLLMRelease:
    def test_explicit_llm_type_is_llm(self):
        assert mrag._is_llm_release(_entry("Claude", "llm"))

    def test_model_type_is_llm(self):
        assert mrag._is_llm_release(_entry("DeepSeek-V3", "model"))

    def test_known_name_without_type_is_llm(self):
        assert mrag._is_llm_release(_entry("Llama", ""))

    def test_known_name_with_none_type_is_llm(self):
        assert mrag._is_llm_release(_entry("Mistral Large", None))

    def test_runtime_name_is_llm(self):
        # Ollama is tagged as a tool upstream but is an LLM-ecosystem release.
        assert mrag._is_llm_release(_entry("Ollama", "tool"))

    def test_browser_is_not_llm(self):
        assert not mrag._is_llm_release(_entry("Chrome", "browser", ["chrome"]))

    def test_os_is_not_llm(self):
        assert not mrag._is_llm_release(_entry("Linux", "os", ["kernel"]))

    def test_missing_fields_do_not_raise(self):
        assert mrag._is_llm_release({}) is False


class TestExpandTerms:
    def test_expansion_is_reflexive(self):
        assert "security" in mrag.expand_terms("security advisory")

    def test_synonym_expansion(self):
        expanded = mrag.expand_terms("security")
        assert "vulnerability" in expanded and "cve" in expanded


class TestLLMAliases:
    def test_provider_aliases_resolve(self):
        for alias, canonical in [
            ("chatgpt", "gpt"), ("anthropic", "claude"),
            ("mixtral", "mistral"), ("bard", "gemini"),
        ]:
            assert mrag.VENDOR_ALIASES.get(alias) == canonical


class TestAmbiguousProductNames:
    """Bare substring matching put unrelated software in Tier 1 as "VERIFIED
    LLM / AI Model Releases": the Opus audio codec, the Falcon web framework,
    anything containing "phi", "o1" or "o3"."""

    def test_substring_collision_is_not_llm(self):
        assert not mrag._is_llm_release(_entry("Opusflow Media Encoder"))
        assert not mrag._is_llm_release(_entry("Graphite"))

    def test_weak_name_without_ai_vendor_is_not_llm(self):
        assert not mrag._is_llm_release(
            {"versionProductName": "Falcon", "versionProductBrand": "CrowdStrike"})
        assert not mrag._is_llm_release(
            {"versionProductName": "Opus", "versionProductBrand": "Xiph.Org"})

    def test_weak_name_with_ai_vendor_is_llm(self):
        assert mrag._is_llm_release(
            {"versionProductName": "Falcon", "versionProductBrand": "TII"})
        assert mrag._is_llm_release(
            {"versionProductName": "Opus 4.5", "versionProductBrand": "Anthropic"})

    def test_strong_name_stands_alone(self):
        assert mrag._is_llm_release(_entry("Llama 3.1"))
        assert mrag._is_llm_release(_entry("DeepSeek V3"))


class TestQueryGate:
    """The LLM feed is only reachable through a per-term search endpoint, so
    each term costs a round trip. Non-AI questions must not pay for it."""

    def test_ai_questions_pass(self):
        assert mrag.query_mentions_llm("what is the latest llama release?")
        assert mrag.query_mentions_llm("Did Anthropic ship a new model?")
        assert mrag.query_mentions_llm("newest LLM releases")

    def test_non_ai_questions_are_gated_out(self):
        assert not mrag.query_mentions_llm("latest ubuntu kernel version")
        assert not mrag.query_mentions_llm("is postgres 17 out yet")

    def test_gate_short_circuits_before_any_http(self, monkeypatch):
        called = []

        class _Boom:
            @staticmethod
            def get(*a, **k):
                called.append(a)
                raise AssertionError("network touched for a non-AI query")

        monkeypatch.setitem(__import__("sys").modules, "requests", _Boom)
        assert mrag.fetch_llm_releases("latest ubuntu kernel version") == []
        assert not called


class TestRelevanceThreshold:
    """min_overlap=1 over synonym-expanded terms admitted every row, because
    "release"/"update" are injected into nearly every expansion."""

    def test_generic_terms_do_not_clear_the_threshold(self):
        assert "release" in mrag.LLM_GENERIC_TERMS
        assert "update" in mrag.LLM_GENERIC_TERMS
        assert "latest" in mrag.LLM_GENERIC_TERMS


class TestTierMembership:
    def test_llm_releases_is_tier1(self):
        assert "llm_releases" in mrag.TIER1

    def test_tier1_label_and_membership_agree(self):
        for src in mrag.TIER1:
            label, _ = mrag.get_source_label(src)
            assert label == "✅ VERIFIED", f"{src} is in TIER1 but labelled {label}"
