#!/usr/bin/env bash
# Phase 4 — independent judge. Closes threat T2 (the default judge shares a
# model family with the pipeline's rewriter). Needs OPENAI_API_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."
DATASET="${1:?usage: phase_judge.sh <dataset.json> <snapshot-dir>}"
SNAP="${2:?usage: phase_judge.sh <dataset.json> <snapshot-dir>}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY first}"
MARAG_RERANK=embed ./venv311/bin/python -m eval_harness.run_eval \
  --dataset "$DATASET" --generators marag,single_agent \
  --judge openai:gpt-4o --judge-pool --corpus "replay:$SNAP"
echo "Now report BOTH judges' system rankings side by side, plus Cohen's kappa."
