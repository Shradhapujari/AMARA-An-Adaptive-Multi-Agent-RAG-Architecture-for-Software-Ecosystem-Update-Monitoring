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
