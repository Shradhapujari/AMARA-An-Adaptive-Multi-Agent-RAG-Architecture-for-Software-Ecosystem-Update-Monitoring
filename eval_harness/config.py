"""Central configuration for the evaluation harness."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "results")


@dataclass
class EvalConfig:
    # Which systems to evaluate. See generators.build_generators for the grammar.
    generators: List[str] = field(default_factory=lambda: [
        "marag",
        "single_agent",
        "raw:ollama:llama3.1",
        "raw:ollama:mistral",
    ])
    # Model used for judging (qrels + answer scoring). Keep it distinct from the
    # systems under test to reduce self-evaluation bias.
    judge: str = "ollama:llama3.1"
    # Dataset file (relative to project root) and how many questions to use.
    dataset: str = "validation_gt.json"
    limit: int = 0                      # 0 = all
    # Established-benchmark mode. When set ("crag" or "generic"), the dataset is
    # loaded via benchmarks.load_benchmark and answers are additionally scored
    # with deterministic CRAG-style labelling (correct/incorrect/missing),
    # independent of our own Evaluator and of the LLM judge.
    benchmark: str = ""
    # Retrieval / metric settings.
    top_k: int = 4
    ks: List[int] = field(default_factory=lambda: [1, 3, 5])
    seed: int = 42
    # Judge every pre-rerank candidate, not only the top_k that survived it.
    # Buys pool recall -- the ceiling any reranker could reach on this fetch --
    # at the cost of one judge call per extra candidate, so it is off by default
    # and worth turning on for the small ground-truth sets.
    judge_pool: bool = False
    # Frozen-corpus control, "record:<dir>" or "replay:<dir>"; see
    # corpus_snapshot.py. Empty means read the live endpoints, which makes two
    # runs incomparable and so must never be used for an ablation.
    corpus: str = os.environ.get("MARAG_CORPUS", "")
    # Where to write the run.
    results_dir: str = RESULTS_DIR
