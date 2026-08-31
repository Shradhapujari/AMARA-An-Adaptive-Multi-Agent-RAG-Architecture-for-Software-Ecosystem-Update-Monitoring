#!/usr/bin/env bash
# Phase 4, the reachable half. `phase_judge.sh` closes threat T2 (the judge
# shares a model family with the pipeline's rewriter) against OpenAI's GPT-4o,
# and needs OPENAI_API_KEY -- unset on this machine, and the `openai` package
# is not installed either. That check cannot run here.
#
# This closes the same threat with what IS available: `qwen2.5:7b-instruct`,
# already pulled locally and from a different model family than llama3.1
# (Alibaba's Qwen vs Meta's Llama), used as a second judge over answers a run
# already generated and stored. No new generation, no API key, no GPU time
# beyond judging. It is a weaker independence guarantee than a closed
# cross-vendor model (both are still open-weight, locally-hosted LLMs), but it
# is a real second opinion and it is the one this environment can actually run.
#
# This methodology already produced one finding:
# eval_harness/sample_results/benchmark_100_3arm/judge_robustness.md re-judged
# the marag_llm-vs-marag format comparison and found it survives (delta +0.111
# under llama3.1, +0.107 under qwen2.5, significant under both). This script
# is that same tool, `judge_robustness.py`, pointed at the actual system-level
# comparison -- marag vs single_agent -- instead.
#
#   scripts/phase4_qwen_check.sh <run_dir> [out.md]
set -euo pipefail

main() {
cd "$(dirname "$0")/.."
RUN_DIR="${1:?usage: phase4_qwen_check.sh <run_dir> [out.md]}"
# judge_robustness.py joins this against RUN_DIR itself (os.path.join(run_dir,
# out)), so this must be a bare filename or a path relative to the run
# directory -- NOT repo-root-relative ("results/..."). Passing "results/foo.md"
# here made it try to create run_dir/results/foo.md, whose parent doesn't
# exist, and crashed with FileNotFoundError after judging all 100 questions --
# the judging itself succeeded and only the write failed. Landing the report
# inside the run directory it re-judged is also the right place for it: that
# is where every other per-run artifact (config.json, per_query.jsonl) lives.
OUT="${2:-$(basename "$RUN_DIR")_qwen_check.md}"

./venv311/bin/python judge_robustness.py "$RUN_DIR" \
    --judge ollama:qwen2.5:7b-instruct \
    --arms marag,single_agent \
    --metric faithfulness \
    --sample 0 \
    --out "$OUT"

echo "Wrote $OUT"
}

main "$@"
exit $?
