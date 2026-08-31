"""extract_vendor must not depend on PYTHONHASHSEED.

Found via a real Phase 5 frozen-corpus ablation: `check_runs.py`'s pool-identity
gate failed at 184/200 (not 200/200) between two arms replaying the same
corpus_snapshot with zero external misses on either arm. The corpus was frozen;
the vendor DECISION was not. `extract_vendor` iterated `set(words)` when
checking exact-word vendor matches, then broke score ties by insertion order --
so a query containing two words that are both registered vendor names
("rust-lang rust v1.92.0 ship" matches both "rust" and, spuriously, "release"
from "release channel") could resolve to either one depending on the process's
hash seed, which is randomized per process by default. That silently changed
which vendor-specific endpoints got queried, producing a different candidate
pool for byte-identical input across separate `run_eval` invocations.

These tests run under several explicit PYTHONHASHSEED values via a subprocess,
because re-exec'ing with a different seed inside one process has no effect --
the seed is fixed at interpreter startup.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MRAG = ROOT / "multiagent_rag_v3.py"

SEEDS = ["0", "1", "2", "3", "4", "17", "42", "1000"]

_PROBE = '''
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("mrag", {mrag!r})
mrag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mrag)
print(json.dumps(mrag.extract_vendor({query!r})))
'''


def _run_with_seed(seed: str, query: str) -> list:
    src = _PROBE.format(mrag=str(MRAG), query=query)
    out = subprocess.run(
        [sys.executable, "-c", src],
        cwd=ROOT, env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    lines = [l for l in out.stdout.splitlines() if l.strip().startswith("[")]
    assert lines, f"no JSON output for seed={seed}: {out.stdout!r} {out.stderr!r}"
    import json
    return json.loads(lines[-1])


class TestVendorExtractionIsSeedInvariant:
    def test_the_exact_reported_query(self):
        """This is the query that actually flipped between arms in Phase 5."""
        query = "What release channel did rust-lang rust v1.92.0 ship on?"
        results = {tuple(_run_with_seed(s, query)) for s in SEEDS}
        assert len(results) == 1, (
            f"extract_vendor is not seed-invariant: got {results} across "
            f"seeds {SEEDS}"
        )

    def test_a_second_ambiguous_query(self):
        """Different word pair, same class of tie: both are exact-name hits."""
        query = "Should I upgrade to Arch v2026.01.01?"
        results = {tuple(_run_with_seed(s, query)) for s in SEEDS}
        assert len(results) == 1, (
            f"extract_vendor is not seed-invariant: got {results} across "
            f"seeds {SEEDS}"
        )


class TestVendorExtractionUnitLevel:
    """Same property, without paying for a subprocess per case."""

    @classmethod
    def setup_class(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("mrag_unit", MRAG)
        cls.mrag = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mrag)

    def test_sorted_not_raw_set_iteration(self):
        """Regression pin on the mechanism, not just the symptom: the exact-word
        match steps must iterate a sorted sequence, so a source read shows the
        fix in place even if the seed-invariance test above is ever skipped."""
        import inspect
        src = inspect.getsource(self.mrag.extract_vendor)
        assert "words = set(" not in src, (
            "extract_vendor iterates a raw set again -- this reintroduces "
            "PYTHONHASHSEED-dependent vendor selection on tied matches"
        )

    def test_still_finds_the_intended_vendor_when_unambiguous(self):
        assert self.mrag.extract_vendor("Is Ubuntu v13.3.0 out yet?") == ["ubuntu"]
