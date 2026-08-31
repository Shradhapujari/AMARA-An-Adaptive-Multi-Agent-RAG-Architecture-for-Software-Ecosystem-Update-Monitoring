#!/usr/bin/env bash
# Phase 0 — environment is real. Run this first, and after any dependency change.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv311/bin/python

echo "== interpreter (expect 3.11.15)";      $PY -V
echo "== ollama models (need llama3.1, mistral, nomic-embed-text)"
curl -s -m 5 http://localhost:11434/api/tags \
  | $PY -c "import json,sys;print(sorted(m['name'] for m in json.load(sys.stdin)['models']))"
echo "== test suite";                        $PY -m pytest tests eval_harness -q
echo "== provenance capture for the artifact"
$PY -m pip freeze > results/env_pip_freeze.txt 2>/dev/null || true
curl -s http://localhost:11434/api/tags > results/env_ollama_tags.json 2>/dev/null || true
echo "PHASE 0 OK"
