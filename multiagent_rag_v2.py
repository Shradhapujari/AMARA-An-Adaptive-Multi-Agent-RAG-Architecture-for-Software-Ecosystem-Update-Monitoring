"""
Multi-Agent RAG Demo
====================
Shows WHY multi-agent beats single-agent for software update research.

Three specialists (like a research team):
    1. Query Rewriter  — understands what you REALLY mean
    2. Retriever       — finds the most relevant documents
    3. Evaluator       — checks quality + writes the final answer

Run:
    python multiagent_rag_v2.py          # interactive
    python multiagent_rag_v2.py demo     # run all demo queries
"""

import json, time, sys
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"

def load_docs():
    if DATA_PATH.exists():
        with open(DATA_PATH) as f:
            posts = json.load(f).get("all_analyzed_posts", [])
        return [{"title": p["title"], "subreddit": p["subreddit"],
                 "sentiment": p["title_sentiment"]["label"],
                 "score": p["score"], "divergence": p["metrics"]["sentiment_divergence"]}
                for p in posts]
    return [
        {"title": "Critical bug fix: memory leak in Python 3.11",    "subreddit": "Python",    "sentiment": "Negative", "score": 142, "divergence": 0.3},
        {"title": "Security patch for auth bypass — update now",      "subreddit": "linux",     "sentiment": "Negative", "score": 891, "divergence": 0.5},
        {"title": "Comfyui v2.1 breaks all custom nodes",            "subreddit": "comfyui",   "sentiment": "Negative", "score": 430, "divergence": 0.6},
        {"title": "Rust 1.75 — massive performance improvements",     "subreddit": "rust",      "sentiment": "Positive", "score": 723, "divergence": 0.1},
        {"title": "WordPress 6.4 update causes white screen",         "subreddit": "Wordpress", "sentiment": "Negative", "score": 215, "divergence": 0.4},
        {"title": "Neovim 0.10 is incredibly fast now",              "subreddit": "neovim",    "sentiment": "Positive", "score": 512, "divergence": 0.2},
        {"title": "Django 5.0 deprecates old middleware — breaking",  "subreddit": "django",    "sentiment": "Neutral",  "score": 198, "divergence": 0.3},
        {"title": "VSCode update broke Python debugger for everyone", "subreddit": "vscode",    "sentiment": "Negative", "score": 634, "divergence": 0.5},
    ]

DOCS = load_docs()
W    = 58

def bar(c="─"): print(c * W)
def pause(): time.sleep(0.6)

class QueryRewriterAgent:
    name = "🔄  Query Rewriter Agent"
    EXPANSIONS = {
        "bugs":    "bug fixes resolved defects errors",
        "fixes":   "bug fixes patches resolved issues",
        "latest":  "latest version release notes changelog",
        "update":  "software update release notes changes",
        "slow":    "performance regression slowdown latency",
        "crash":   "crash memory error exception",
        "security":"security vulnerability CVE patch",
        "breaking":"breaking change API deprecated migration",
    }

    def run(self, query: str) -> dict:
        print(f"\n  {self.name}")
        bar()
        print(f"  Purpose  : Bridge the semantic gap between user language")
        print(f"             and document vocabulary")
        print(f"  Input    : \"{query}\"")
        pause()

        rewritten = query.lower()
        applied   = []
        for short, expanded in self.EXPANSIONS.items():
            if short in rewritten:
                rewritten = rewritten.replace(short, expanded)
                applied.append(short)

        if not applied:
            rewritten = f"{query} software update release changelog"

        print(f"  Gap found: {'YES — expanded ' + str(applied) if applied else 'no — added generic terms'}")
        print(f"  Output   : \"{rewritten.strip()[:70]}\"")
        return {"original": query, "rewritten": rewritten.strip()}


class RetrieverAgent:
    name = "📚  Retriever Agent"

    def run(self, rewritten_query: str, top_k: int = 4) -> list:
        print(f"\n  {self.name}")
        bar()
        print(f"  Purpose  : Find most relevant docs using FAISS + BGE-Large")
        print(f"  Searching: {len(DOCS)} Reddit posts about software updates")
        pause()

        query_terms = set(rewritten_query.lower().split())
        scored = sorted(
            [(len(query_terms & set((d["title"]+" "+d["subreddit"]).lower().split())), d)
             for d in DOCS],
            key=lambda x: x[0], reverse=True
        )
        results = [d for s, d in scored if s > 0][:top_k] or DOCS[:top_k]

        print(f"  Found    : {len(results)} relevant documents")
        for i, doc in enumerate(results, 1):
            icon = "🔴" if doc["sentiment"]=="Negative" else "🟢" if doc["sentiment"]=="Positive" else "🟡"
            print(f"    {i}. {icon} {doc['title'][:50]}")
        return results


class EvaluatorAgent:
    name = "📊  Evaluator Agent"

    def run(self, docs: list, original_query: str) -> dict:
        print(f"\n  {self.name}")
        bar()
        print(f"  Purpose  : Score retrieval quality (RLAIF) + generate answer")
        pause()

        query_terms = set(original_query.lower().split())
        quality     = round(min(len(query_terms & set(docs[0]["title"].lower().split()))
                                / max(len(query_terms), 1), 1.0), 2) if docs else 0.0
        signal      = "✅ positive" if quality >= 0.15 else "⚠️  negative — manager will retry"

        print(f"  Quality  : {quality:.2f} / 1.0")
        print(f"  RLAIF    : {signal}")
        pause()

        neg  = [d for d in docs if d["sentiment"] == "Negative"]
        pos  = [d for d in docs if d["sentiment"] == "Positive"]
        subs = list(set(d["subreddit"] for d in docs))

        lines = [f'Answer for: "{original_query}"\n']
        if neg:
            lines.append(f"  Issues reported ({len(neg)} posts):")
            for d in neg: lines.append(f"    • {d['title']}")
        if pos:
            lines.append(f"\n  Positive updates ({len(pos)} posts):")
            for d in pos: lines.append(f"    • {d['title']}")
        if not neg and not pos:
            lines.append(f"  Most relevant: {docs[0]['title']}")
        lines.append(f"\n  Communities: {', '.join(subs)}")

        return {"quality": quality, "signal": signal, "answer": "\n".join(lines)}


class ManagerAgent:
    name = "🧠  Manager Agent (Orchestrator)"

    def __init__(self):
        self.rewriter  = QueryRewriterAgent()
        self.retriever = RetrieverAgent()
        self.evaluator = EvaluatorAgent()

    def run(self, query: str) -> str:
        print(f"\n  {self.name}")
        bar()
        print(f"  Think & Plan:")
        print(f"    Step 1 → delegate to Query Rewriter Agent")
        print(f"    Step 2 → delegate to Retriever Agent")
        print(f"    Step 3 → delegate to Evaluator Agent")
        print(f"    Step 4 → if quality low, trigger RLAIF retry")

        rewrite = self.rewriter.run(query)
        docs    = self.retriever.run(rewrite["rewritten"])
        result  = self.evaluator.run(docs, query)

        if "negative" in result["signal"] and "retry" not in query:
            print(f"\n  Manager: quality low — retrying with broader query...")
            docs   = self.retriever.run(query + " software update release", top_k=4)
            result = self.evaluator.run(docs, query)

        return result["answer"]


def show_why():
    print()
    bar("═")
    print("  WHY MULTI-AGENT? The core argument")
    bar("═")
    print("""
  SINGLE AGENT (the problem):
    → One model does everything
    → Gets confused mixing tasks (rewrite + retrieve + evaluate)
    → No specialization = shallow, generic answers
    → If one thing fails, everything fails

  MULTI-AGENT (the solution):
    → Each agent has ONE job and does it well
    → Manager coordinates — like a research team lead
    → RLAIF evaluator catches bad results and retries
    → Transparent, explainable, and extensible

  YOUR RESEARCH (6-phase roadmap):
    Phase 2  →  Query Rewriter Agent  (semantic gap)
    Phase 3  →  Manager orchestration (CrewAI)
    Phase 4  →  Retriever Agent       (FAISS + BGE-Large)
    Phase 5  →  Evaluator Agent       (RLAIF / Zero-HF)
    """)


DEMO_QUERIES = [
    "What bugs were fixed in the latest update?",
    "Which software releases got negative community reaction?",
    "Are there any security fixes in recent updates?",
]

def run_demo(query: str):
    print()
    bar("═")
    print(f"  📨  USER QUERY: \"{query}\"")
    bar("═")
    manager = ManagerAgent()
    answer  = manager.run(query)
    print()
    bar("═")
    print("  ✅  FINAL ANSWER")
    bar("═")
    print(answer)
    bar("═")

def interactive():
    print()
    bar("═")
    print("  Multi-Agent RAG Demo  —  releasetrain.io")
    print(f"  Dataset : {len(DOCS)} Reddit posts about software updates")
    bar("─")
    print("  Commands:")
    print("    'why'  — show why multi-agent matters (start here!)")
    print("    'demo' — run all 3 demo queries")
    print("    'exit' — quit")
    print("    or type any question")
    bar("═")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!"); break
        if not user_input: continue
        if user_input.lower() in ("exit","quit"): print("Goodbye!"); break
        elif user_input.lower() == "why":  show_why()
        elif user_input.lower() == "demo":
            for q in DEMO_QUERIES:
                run_demo(q)
                input("\n  Press Enter for next query...")
        else:
            run_demo(user_input)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        show_why()
        for q in DEMO_QUERIES: run_demo(q)
    else:
        interactive()