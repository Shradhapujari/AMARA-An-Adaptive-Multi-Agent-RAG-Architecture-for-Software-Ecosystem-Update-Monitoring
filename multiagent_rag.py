"""
Multi-Agent RAG Demo — Clean Presentation Version
==================================================
Shows WHY multi-agents matter using Reddit software update data.

Architecture:
  User Question
       ↓
  Manager Agent  ← coordinates everything
       ↓              ↓              ↓
  🔵 Rewriter    🟢 Retriever   🟠 Evaluator
  fixes query    finds docs     scores & answers

Run:
    venv311/bin/python3 multiagent_rag.py
"""

import json
import time
from pathlib import Path

# ──────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────
DATA_PATH = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"

def load_docs():
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH) as f:
        data = json.load(f)
    return [{
        "title":     p.get("title", ""),
        "subreddit": p.get("subreddit", ""),
        "text":      p.get("title", "") + " — " + p.get("title_sentiment", {}).get("label", "neutral"),
        "url":       p.get("url", ""),
        "sentiment": p.get("metrics", {}).get("community_avg_sentiment", 0),
    } for p in data.get("all_analyzed_posts", [])]

DOCS = load_docs()

# ──────────────────────────────────────────────
# AGENT 1 — QUERY REWRITER
# Job: fix vague user questions
# ──────────────────────────────────────────────
def rewriter_agent(query: str) -> dict:
    expansions = {
        "latest update": "software update changelog bug fixes features",
        "latest ver":    "latest version release notes changelog",
        "bugs":          "bug fixes defects resolved issues",
        "fixes":         "bug fixes patches resolved defects",
        "slow":          "performance regression slowdown latency",
        "crash":         "crash memory error failure",
        "security":      "security vulnerability CVE patch",
        "negative":      "negative sentiment community reaction complaints",
        "feel":          "sentiment opinion community reaction",
    }
    rewritten = query.lower()
    applied = []
    for short, expanded in expansions.items():
        if short in rewritten:
            rewritten = rewritten.replace(short, expanded)
            applied.append(short)
    if not applied:
        rewritten = f"{query} software update changelog"

    return {
        "original":  query,
        "rewritten": rewritten.strip(),
        "improved":  len(applied) > 0,
        "keywords_expanded": applied if applied else ["generic"],
    }


# ──────────────────────────────────────────────
# AGENT 2 — RETRIEVER
# Job: find the most relevant Reddit posts
# ──────────────────────────────────────────────
def retriever_agent(rewritten_query: str, top_k: int = 3) -> list:
    terms = set(rewritten_query.lower().split())
    scored = []
    for doc in DOCS:
        text  = (doc["title"] + " " + doc.get("text", "") + " " + doc.get("subreddit", "")).lower()
        score = len(terms & set(text.split()))
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [d for _, d in scored[:top_k]]
    if not results:
        results = DOCS[:top_k]
    return results


# ──────────────────────────────────────────────
# AGENT 3 — EVALUATOR
# Job: score quality and write the final answer
# ──────────────────────────────────────────────
def evaluator_agent(docs: list, original_query: str) -> dict:
    if not docs:
        return {"answer": "No results found.", "quality": "low", "signal": "⚠️ retry"}

    terms   = set(original_query.lower().split())
    top     = docs[0]
    overlap = len(terms & set(top.get("title", "").lower().split()))
    quality = "good" if overlap >= 2 else "low"

    lines  = [f"    • [{d.get('subreddit','?')}] {d['title'][:60]}" for d in docs]
    answer = "\n".join(lines)

    return {
        "answer":  answer,
        "quality": quality,
        "signal":  "✅ good match" if quality == "good" else "⚠️ low match",
    }


# ──────────────────────────────────────────────
# MANAGER — coordinates all 3 agents
# ──────────────────────────────────────────────
def manager_agent(question: str) -> str:
    # Step 1 — Rewriter fixes the query
    rewrite_result = rewriter_agent(question)

    # Step 2 — Retriever finds relevant posts
    docs = retriever_agent(rewrite_result["rewritten"])

    # Step 3 — Evaluator scores and answers
    eval_result = evaluator_agent(docs, question)

    return rewrite_result, docs, eval_result


# ──────────────────────────────────────────────
# DEMO QUERIES
# ──────────────────────────────────────────────
DEMO_QUERIES = [
    "What bugs were fixed in the latest software update?",
    "How do users feel about the latest ver of comfyui?",
    "Which releases had the most negative community reaction?",
]


# ──────────────────────────────────────────────
# CLEAN PRESENTATION OUTPUT
# ──────────────────────────────────────────────
def line(char="═", w=60):
    print(char * w)

def run_query(question: str, number: int, total: int):
    line()
    print(f"  QUERY {number}/{total}")
    print(f"  ❓ {question}")
    line("─")

    rewrite_result, docs, eval_result = manager_agent(question)

    # Show Rewriter Agent result
    print(f"  🔵 REWRITER AGENT")
    print(f"     Original : {rewrite_result['original']}")
    print(f"     Rewritten: {rewrite_result['rewritten'][:70]}...")
    print(f"     Expanded : {', '.join(rewrite_result['keywords_expanded'])}")
    line("─")

    # Show Retriever Agent result
    print(f"  🟢 RETRIEVER AGENT  — found {len(docs)} relevant posts")
    for d in docs:
        print(f"     • [r/{d.get('subreddit','?')}] {d['title'][:55]}")
    line("─")

    # Show Evaluator Agent result
    print(f"  🟠 EVALUATOR AGENT  — quality: {eval_result['quality']}  {eval_result['signal']}")
    line("─")

    # Final Answer
    print(f"  ✅ FINAL ANSWER:")
    print(eval_result["answer"])
    line()
    print()


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":

    # Header
    line()
    print("  MULTI-AGENT RAG DEMO")
    print("  Why Multi-Agents? Each agent is a specialist.")
    line("─")
    print("  🔵 Rewriter Agent  — fixes vague user queries")
    print("  🟢 Retriever Agent — finds relevant Reddit posts")
    print("  🟠 Evaluator Agent — scores quality & writes answer")
    print("  ⚫ Manager         — coordinates all three")
    line("─")
    print(f"  Dataset: {len(DOCS)} Reddit posts about software updates")
    line()
    print()

    # Run all 3 queries
    for i, query in enumerate(DEMO_QUERIES, 1):
        run_query(query, i, len(DEMO_QUERIES))
        time.sleep(0.5)

    # Footer
    line()
    print("  DEMO COMPLETE ✅")
    line("─")
    print("  Key Takeaway:")
    print("  One agent doing everything = confused & slow")
    print("  Three specialists + one manager = accurate & clear")
    line()
