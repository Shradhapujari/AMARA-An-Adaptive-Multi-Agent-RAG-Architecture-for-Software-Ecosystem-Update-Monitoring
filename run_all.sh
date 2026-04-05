#!/bin/bash
# Run all demo files in order
# Usage: bash run_all.sh

PYTHON="venv311/bin/python3"
W="============================================================"

echo $W
echo "  RUNNING ALL DEMO FILES"
echo $W

echo ""
echo ">>> 1/3  DemoMain3.py — Single Agent Demo"
echo $W
$PYTHON DemoMain3.py
echo ""

echo ">>> 2/3  rag_agent_smolagents.py — Single RAG Agent"
echo $W
$PYTHON rag_agent_smolagents.py
echo ""

echo ">>> 3/3  multiagent_rag.py — Multi-Agent RAG System"
echo $W
$PYTHON multiagent_rag.py
echo ""

echo $W
echo "  ALL DEMOS COMPLETE"
echo $W
