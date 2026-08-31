#!/usr/bin/env bash
# Ranking ablation on a frozen corpus. Used by Phase 3 (validation_gt) and
# Phase 5 (benchmark_100 / benchmark_300).
#
#   scripts/phase_ablation.sh <dataset.json> <snapshot-dir>
#
# Pass 0 populates the snapshot; passes 1-3 replay it, so the three arms differ
# only in MARAG_RERANK. Pass 0 reports frozen=false by construction -- it is a
# population pass, not an arm, and carries no claim.
set -euo pipefail
cd "$(dirname "$0")/.."
DATASET="${1:?usage: phase_ablation.sh <dataset.json> <snapshot-dir>}"
SNAP="${2:?usage: phase_ablation.sh <dataset.json> <snapshot-dir>}"
PY=./venv311/bin/python
COMMON="--dataset $DATASET --generators marag,single_agent --judge ollama:llama3.1 --judge-pool"

echo "##### WARM/RECORD pass | $(date +%H:%M:%S)"
MARAG_RERANK=embed $PY -m eval_harness.run_eval $COMMON --corpus "replay:$SNAP"

for arm in none bm25 embed; do
  echo "##### ARM $arm | $(date +%H:%M:%S)"
  MARAG_RERANK=$arm $PY -m eval_harness.run_eval $COMMON --corpus "replay:$SNAP"
done
echo "##### DONE | $(date +%H:%M:%S) — now run: scripts/check_runs.py"
