"""
RAG Agent — smolagents ToolCallingAgent (simplified)
=====================================================
Fixed version of rag_agent_smolagents.py

Problem with old version:
    Used CodeAgent — writes + executes Python code
    Llama 3.1 got confused, tried wikipedia_search, looped forever

This version:
    Uses ToolCallingAgent — just picks a tool and calls it directly
    Much simpler, much more reliable with Llama 3.1
    Matches HuggingFace Unit 1 diagram exactly

Run:
    python rag_smolagents_v2.py
"""

import json
from pathlib import Path
from smolagents import ToolCallingAgent, LiteLLMModel, tool

# ─────────────────────────────────────────────────────────────
# DATASET
# ─────────────────────────────────────────────────────────────

DATA_PATH = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"

def load_docs():
    if DATA_PATH.exists():
        with open(DATA_PATH) as f:
            posts = json.load(f).get("all_analyzed_posts", [])
        print(f"✅  Loaded {len(posts)} real Reddit posts")
        return [{
            "title":     p["title"],
            "subreddit": p["subreddit"],
            "sentiment": p["title_sentiment"]["label"],
            "divergence": p["metrics"]["sentiment_divergence"],
            "url":       p.get("url", ""),
        } for p in posts]
    print("⚠️  Using mock data")
    return [
        {"title": "Critical bug fix: memory leak in Python 3.11",    "subreddit": "Python",    "sentiment": "Negative", "divergence": 0.3, "url": ""},
        {"title": "Security patch for auth bypass — update now",      "subreddit": "linux",     "sentiment": "Negative", "divergence": 0.5, "url": ""},
        {"title": "Comfyui v2.1 breaks all custom nodes",            "subreddit": "comfyui",   "sentiment": "Negative", "divergence": 0.6, "url": ""},
        {"title": "Rust 1.75 — massive performance improvements",     "subreddit": "rust",      "sentiment": "Positive", "divergence": 0.1, "url": ""},
        {"title": "WordPress 6.4 update causes white screen",         "subreddit": "Wordpress", "sentiment": "Negative", "divergence": 0.4, "url": ""},
        {"title": "Neovim 0.10 is incredibly fast now",              "subreddit": "neovim",    "sentiment": "Positive", "divergence": 0.2, "url": ""},
        {"title": "Django 5.0 deprecates old middleware",             "subreddit": "django",    "sentiment": "Neutral",  "divergence": 0.3, "url": ""},
        {"title": "VSCode update broke Python debugger for everyone", "subreddit": "vscode",    "sentiment": "Negative", "divergence": 0.5, "url": ""},
    ]

DOCS = load_docs()

# ─────────────────────────────────────────────────────────────
# TOOLS  (simple, clear, no ambiguity)
# ─────────────────────────────────────────────────────────────

@tool
def search_software_updates(query: str) -> str:
    """
    Search Reddit posts about software updates, bugs, releases and security patches.
    Use this for ANY question about software updates, bugs, releases, or community reactions.
    This is the ONLY search tool available — always use this first.
    Args:
        query: what to search for (e.g. "bug fixes", "security patches", "negative reactions")
    """
    query_terms = set(query.lower().split())
    scored = []
    for doc in DOCS:
        text    = (doc["title"] + " " + doc["subreddit"] + " " + doc["sentiment"]).lower()
        overlap = len(query_terms & set(text.split()))
        scored.append((overlap, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [d for _, d in scored[:5]]

    output = []
    for d in results:
        icon = "🔴" if d["sentiment"] == "Negative" else "🟢" if d["sentiment"] == "Positive" else "🟡"
        output.append({
            "title":      d["title"],
            "subreddit":  f"r/{d['subreddit']}",
            "sentiment":  f"{icon} {d['sentiment']}",
            "divergence": round(d["divergence"], 3),
        })
    return json.dumps(output, indent=2)


@tool
def get_most_negative_posts(top_n: str = "5") -> str:
    """
    Get the Reddit posts with the most negative community sentiment about software updates.
    Use this when asked about negative reactions, frustrated users, or bad releases.
    Args:
        top_n: how many posts to return (default "5")
    """
    try:
        n = int(str(top_n).strip())
    except Exception:
        n = 5
    n = min(n, 10)

    neg_docs = [d for d in DOCS if d["sentiment"] == "Negative"]
    neg_docs.sort(key=lambda d: d["divergence"], reverse=True)

    results = []
    for d in neg_docs[:n]:
        results.append({
            "title":      d["title"],
            "subreddit":  f"r/{d['subreddit']}",
            "sentiment":  "🔴 Negative",
            "divergence": round(d["divergence"], 3),
            "meaning":    "author frustrated, community reacted differently" if d["divergence"] > 0.3 else "negative overall",
        })
    return json.dumps(results, indent=2)


@tool
def get_dataset_overview() -> str:
    """
    Get an overview of the entire Reddit software updates dataset.
    Use this when asked about the dataset, total posts, or general statistics.
    """
    neg = sum(1 for d in DOCS if d["sentiment"] == "Negative")
    pos = sum(1 for d in DOCS if d["sentiment"] == "Positive")
    neu = sum(1 for d in DOCS if d["sentiment"] == "Neutral")
    subs = list(set(d["subreddit"] for d in DOCS))

    return json.dumps({
        "total_posts":        len(DOCS),
        "negative_posts":     neg,
        "positive_posts":     pos,
        "neutral_posts":      neu,
        "subreddits_covered": len(subs),
        "top_subreddits":     subs[:10],
        "sentiment_model":    "VADER",
        "data_source":        "releasetrain.io Reddit API",
    }, indent=2)

# ─────────────────────────────────────────────────────────────
# AGENT  — ToolCallingAgent (NOT CodeAgent)
# ─────────────────────────────────────────────────────────────

model = LiteLLMModel(
    model_id="ollama/llama3.1",
    api_base="http://localhost:11434",
)

agent = ToolCallingAgent(
    tools=[search_software_updates, get_most_negative_posts, get_dataset_overview],
    model=model,
    max_steps=4,
    verbosity_level=1,
)

# ─────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────

W = 58

def bar(c="═"): print(c * W)

DEMO_QUERIES = [
    "What bugs were fixed in the latest software update?",
    "Which software releases got the most negative community reaction?",
    "Give me an overview of the dataset",
]

def run(query: str):
    print()
    bar()
    print(f"  📨  USER REQUEST")
    print(f"  {query}")
    bar("─")
    print(f"  🧠  Think & Plan → Select Tools → Act")
    bar("─")
    try:
        result = agent.run(query)
        print()
        bar()
        print("  ✅  FINAL ANSWER")
        bar("─")
        print(result)
        bar()
    except Exception as e:
        print(f"  ❌  Error: {e}")

def interactive():
    print()
    bar()
    print("  RAG Agent — smolagents ToolCallingAgent")
    print(f"  Dataset : {len(DOCS)} Reddit posts")
    print(f"  Model   : Llama 3.1 via Ollama")
    print(f"  Tools   : search_software_updates | get_most_negative_posts | get_dataset_overview")
    bar("─")
    print("  Commands: 'demo' | 'exit' | any question")
    bar()

    while True:
        try:
            q = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!"); break
        if not q: continue
        if q.lower() in ("exit", "quit"): print("Goodbye!"); break
        elif q.lower() == "demo":
            for dq in DEMO_QUERIES:
                run(dq)
        else:
            run(q)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        for q in DEMO_QUERIES: run(q)
    else:
        interactive()
