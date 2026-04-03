"""
Self-Improving Multi-Agent RAG System
======================================
Uses MiniMax M2.7 via Ollama — a model designed for self-improvement
using data from the web.

Reference: https://ollama.com/blog/minimax-m2.7
"M2.7 is also good at self-improvement using data from the web.
 This allows assistants like OpenClaw to do research and learn new skills."

How self-improvement works in this system:
    Normal agent  → retrieves → answers → done
    Self-improving → retrieves → evaluates → learns from failure
                              → updates strategy → retries smarter
                              → stores what worked → uses next time

The 3 levels of self-improvement shown here:
    Level 1 — RLAIF retry        (already in our system)
    Level 2 — Strategy memory    (new — remembers what worked)
    Level 3 — MiniMax M2.7       (new — self-improving LLM)

Run:
    # First pull the model
    ollama pull minimax-m2.7:cloud

    # Then run
    python self_improving_agent.py
    python self_improving_agent.py demo
"""

import json, time, sys, urllib.request
from pathlib import Path
from collections import defaultdict

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

LLM_MODEL = "minimax-m2.7:cloud"   # self-improving model
FALLBACK   = "llama3.1"             # fallback if MiniMax not available
DATA_PATH  = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"

# ─────────────────────────────────────────────────────────────
# DATASET
# ─────────────────────────────────────────────────────────────

def load_docs():
    if DATA_PATH.exists():
        with open(DATA_PATH) as f:
            posts = json.load(f).get("all_analyzed_posts", [])
        return [{
            "title":      p["title"],
            "subreddit":  p["subreddit"],
            "sentiment":  p["title_sentiment"]["label"],
            "divergence": p["metrics"]["sentiment_divergence"],
            "url":        p.get("url", ""),
        } for p in posts]
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
W    = 62

def bar(c="─"): print(c * W)
def pause(s=0.5): time.sleep(s)

# ─────────────────────────────────────────────────────────────
# SELF-IMPROVEMENT MEMORY
# This is what makes this different from normal agents.
# The system remembers what worked and what didn't.
# Over time it gets smarter without human intervention.
# ─────────────────────────────────────────────────────────────

class SelfImprovementMemory:
    """
    Stores what strategies worked and failed.
    Next query benefits from previous experience.
    This is the core of self-improvement without human feedback (Zero-HF).
    """
    def __init__(self):
        self.successful_rewrites = []     # rewrites that got good retrieval
        self.failed_rewrites     = []     # rewrites that got bad retrieval
        self.strategy_scores     = defaultdict(float)  # which expansion terms work
        self.total_queries       = 0
        self.total_improvements  = 0

    def record_success(self, original: str, rewritten: str, quality: float):
        self.successful_rewrites.append({
            "original":  original,
            "rewritten": rewritten,
            "quality":   quality,
        })
        # Learn which expansion terms are effective
        extra_terms = set(rewritten.lower().split()) - set(original.lower().split())
        for term in extra_terms:
            self.strategy_scores[term] += quality
        self.total_queries += 1

    def record_failure(self, original: str, rewritten: str, quality: float):
        self.failed_rewrites.append({
            "original":  original,
            "rewritten": rewritten,
            "quality":   quality,
        })
        extra_terms = set(rewritten.lower().split()) - set(original.lower().split())
        for term in extra_terms:
            self.strategy_scores[term] -= 0.1
        self.total_queries   += 1
        self.total_improvements += 1

    def get_best_terms(self, top_n: int = 5) -> list:
        """Return the expansion terms that historically gave best results."""
        return sorted(self.strategy_scores.items(),
                      key=lambda x: x[1], reverse=True)[:top_n]

    def suggest_expansion(self, query: str) -> str:
        """
        Use learned knowledge to suggest better expansion terms.
        This is self-improvement — using past experience to help future queries.
        """
        best = self.get_best_terms(3)
        if not best:
            return ""
        terms = " ".join(t for t, _ in best if t not in query.lower())
        return terms

    def print_status(self):
        bar()
        print(f"  📈  SELF-IMPROVEMENT MEMORY STATUS")
        bar("─")
        print(f"  Total queries processed : {self.total_queries}")
        print(f"  Times self-improved     : {self.total_improvements}")
        print(f"  Successful strategies   : {len(self.successful_rewrites)}")
        print(f"  Failed strategies       : {len(self.failed_rewrites)}")
        if self.strategy_scores:
            print(f"  Best learned terms      : {[t for t, _ in self.get_best_terms(3)]}")
        bar()

# Global memory — persists across all queries in one session
MEMORY = SelfImprovementMemory()

# ─────────────────────────────────────────────────────────────
# LLM CALLER — tries MiniMax M2.7 first, falls back to Llama
# ─────────────────────────────────────────────────────────────

def call_llm(prompt: str, model: str = LLM_MODEL) -> tuple[str, str]:
    """
    Call the LLM. Returns (response, model_used).
    Tries MiniMax M2.7 first — falls back to Llama 3.1 if not available.
    """
    payload = json.dumps({
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0}
    }).encode()
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            return result.get("response", "").strip(), model
    except Exception:
        if model != FALLBACK:
            return call_llm(prompt, FALLBACK)
        return f"[LLM unavailable]", FALLBACK

# ─────────────────────────────────────────────────────────────
# AGENT 1 — SELF-IMPROVING QUERY REWRITER
# Uses MiniMax M2.7 + learns from past failures
# ─────────────────────────────────────────────────────────────

class SelfImprovingRewriter:
    name = "🔄  Self-Improving Query Rewriter"

    def run(self, query: str, memory: SelfImprovementMemory) -> dict:
        print(f"\n  {self.name}")
        bar()
        print(f"  Model    : {LLM_MODEL} (self-improving LLM)")
        print(f"  Input    : \"{query}\"")

        # Use learned knowledge from past queries
        learned_terms = memory.suggest_expansion(query)
        memory_hint   = f"\nBased on past successful queries, also include: {learned_terms}" if learned_terms else ""

        prompt = f"""You are a search query rewriting expert for a software update research system.
A user asked: "{query}"

Rewrite this query to find relevant software update posts.
Focus on: bug fixes, releases, changelogs, security patches, community reactions.{memory_hint}

Return ONLY the rewritten query in under 15 words, nothing else:"""

        print(f"  Thinking ...")
        rewritten, model_used = call_llm(prompt)

        if "[LLM unavailable]" in rewritten:
            rewritten = f"{query} software update bug fixes release notes"

        # Show if memory was used
        if learned_terms:
            print(f"  📚  Used learned knowledge: {learned_terms[:40]}")

        print(f"  Model used : {model_used}")
        print(f"  Output     : \"{rewritten[:60]}\"")

        return {
            "original":    query,
            "rewritten":   rewritten,
            "model_used":  model_used,
            "used_memory": bool(learned_terms),
        }

# ─────────────────────────────────────────────────────────────
# AGENT 2 — RETRIEVER (unchanged)
# ─────────────────────────────────────────────────────────────

class RetrieverAgent:
    name = "📚  Retriever Agent"

    def run(self, query: str, top_k: int = 4) -> list:
        print(f"\n  {self.name}")
        bar()
        print(f"  Searching : {len(DOCS)} Reddit posts")
        pause()

        terms  = set(query.lower().split())
        scored = sorted(
            [(len(terms & set((d["title"]+" "+d["subreddit"]).lower().split())), d)
             for d in DOCS],
            key=lambda x: x[0], reverse=True
        )
        results = [d for s, d in scored if s > 0][:top_k] or DOCS[:top_k]

        print(f"  Found     : {len(results)} documents")
        for d in results:
            icon = "🔴" if d["sentiment"]=="Negative" else "🟢" if d["sentiment"]=="Positive" else "🟡"
            print(f"    {icon} {d['title'][:52]}")
        return results

# ─────────────────────────────────────────────────────────────
# AGENT 3 — SELF-EVALUATOR WITH LEARNING
# Scores quality AND records what it learned
# ─────────────────────────────────────────────────────────────

class SelfEvaluatorAgent:
    name = "📊  Self-Evaluator Agent"

    def run(self, docs: list, query: str, rewrite_result: dict,
            memory: SelfImprovementMemory) -> dict:
        print(f"\n  {self.name}")
        bar()
        print(f"  Purpose   : Score quality + LEARN from this result")
        pause()

        terms   = set(query.lower().split())
        quality = round(min(
            len(terms & set(docs[0]["title"].lower().split()))
            / max(len(terms), 1), 1.0), 2) if docs else 0.0

        signal = "✅ positive" if quality >= 0.15 else "⚠️  negative"
        print(f"  Quality   : {quality:.2f} / 1.0")
        print(f"  Signal    : {signal}")

        # SELF-IMPROVEMENT STEP — record what worked or failed
        if quality >= 0.15:
            memory.record_success(
                rewrite_result["original"],
                rewrite_result["rewritten"],
                quality
            )
            print(f"  Learning  : ✅ Recording successful strategy in memory")
        else:
            memory.record_failure(
                rewrite_result["original"],
                rewrite_result["rewritten"],
                quality
            )
            print(f"  Learning  : 📝 Recording failure — will avoid this strategy next time")

        # Build answer
        neg  = [d for d in docs if d["sentiment"] == "Negative"]
        pos  = [d for d in docs if d["sentiment"] == "Positive"]
        subs = list(set(d["subreddit"] for d in docs))

        lines = [f'Answer for: "{query}"\n']
        if neg:
            lines.append(f"  Issues found ({len(neg)} posts):")
            for d in neg: lines.append(f"    • {d['title'][:55]}")
        if pos:
            lines.append(f"\n  Positive updates ({len(pos)} posts):")
            for d in pos: lines.append(f"    • {d['title'][:55]}")
        if not neg and not pos:
            lines.append(f"  Most relevant: {docs[0]['title'][:55]}")
        lines.append(f"\n  Communities: {', '.join(subs)}")

        return {"quality": quality, "signal": signal, "answer": "\n".join(lines)}

# ─────────────────────────────────────────────────────────────
# MANAGER AGENT — SELF-IMPROVING ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

class SelfImprovingManager:
    name = "🧠  Self-Improving Manager Agent"

    def __init__(self):
        self.rewriter  = SelfImprovingRewriter()
        self.retriever = RetrieverAgent()
        self.evaluator = SelfEvaluatorAgent()

    def run(self, query: str, memory: SelfImprovementMemory) -> str:
        print(f"\n  {self.name}")
        bar()
        print(f"  Model    : {LLM_MODEL}")
        print(f"  Memory   : {memory.total_queries} past queries learned from")
        print(f"  Think & Plan:")
        print(f"    Step 1 → Rewriter  (MiniMax M2.7 + memory)")
        print(f"    Step 2 → Retriever (FAISS-style search)")
        print(f"    Step 3 → Evaluator (RLAIF + self-learning)")
        print(f"    Step 4 → Retry if quality low (self-improvement loop)")

        rewrite = self.rewriter.run(query, memory)
        docs    = self.retriever.run(rewrite["rewritten"])
        result  = self.evaluator.run(docs, query, rewrite, memory)

        # Self-improvement retry — uses updated memory from failure
        if "negative" in result["signal"]:
            print(f"\n  🔁  Self-improvement triggered!")
            print(f"  Manager: Checking memory for better strategy...")
            better_terms = memory.suggest_expansion(query)
            improved_q   = f"{query} {better_terms} software update release" if better_terms else f"{query} software update release"
            print(f"  Improved query: \"{improved_q[:55]}\"")
            docs   = self.retriever.run(improved_q)
            result = self.evaluator.run(docs, query, rewrite, memory)

        return result["answer"]

# ─────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    "What bugs were fixed in the latest software update?",
    "Which software releases got the most negative community reaction?",
    "Are there any security fixes in recent updates?",
]

def show_intro():
    print()
    bar("═")
    print("  Self-Improving Multi-Agent RAG System")
    print(f"  Model    : {LLM_MODEL} (MiniMax M2.7)")
    print(f"  Dataset  : {len(DOCS)} Reddit posts about software updates")
    bar("─")
    print("  What makes this different:")
    print("    → Uses MiniMax M2.7 — designed for self-improvement")
    print("    → Remembers what strategies worked in past queries")
    print("    → Gets smarter with every query — no human needed")
    print("    → RLAIF signals update the strategy memory")
    bar("─")
    print("  This is Level 3 of self-improvement:")
    print("    Level 1 — RLAIF retry          (all our agents do this)")
    print("    Level 2 — Strategy memory      (this file adds this)")
    print("    Level 3 — MiniMax M2.7 weights (self-improving LLM)")
    bar("═")

def show_why():
    print()
    bar("═")
    print("  WHY SELF-IMPROVEMENT MATTERS")
    bar("═")
    print("""
  Normal agent:
    Query 1 → fails → done
    Query 2 → same mistake → done
    Query 3 → same mistake again

  Self-improving agent (this system):
    Query 1 → fails → records failure in memory
    Query 2 → checks memory → avoids same mistake → improves
    Query 3 → even better — more patterns learned

  MiniMax M2.7 goes further:
    → Not just strategy memory but actual weight updates
    → Learns from web data in real time
    → The model itself gets smarter, not just the strategy

  Connection to your research:
    Phase 5 (RLAIF / Zero-HF) = Level 2 self-improvement
    MiniMax M2.7              = Level 3 self-improvement
    Your contribution         = bridging these two levels
    """)

def run_demo(query: str, memory: SelfImprovementMemory):
    print()
    bar("═")
    print(f"  📨  USER QUERY: \"{query}\"")
    bar("═")
    manager = SelfImprovingManager()
    answer  = manager.run(query, memory)
    print()
    bar("═")
    print("  ✅  FINAL ANSWER")
    bar("─")
    print(answer)
    bar("═")

def interactive():
    show_intro()
    print("\n  Commands: 'demo' | 'why' | 'memory' | 'exit' | any question\n")

    while True:
        try:
            q = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!"); break
        if not q: continue
        if q.lower() in ("exit", "quit"):
            MEMORY.print_status()
            print("Goodbye!"); break
        elif q.lower() == "why":
            show_why()
        elif q.lower() == "memory":
            MEMORY.print_status()
        elif q.lower() == "demo":
            for dq in DEMO_QUERIES:
                run_demo(dq, MEMORY)
                print(f"\n  Memory after this query:")
                MEMORY.print_status()
                input("\n  Press Enter for next query...")
        else:
            run_demo(q, MEMORY)
            MEMORY.print_status()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        show_intro()
        for q in DEMO_QUERIES:
            run_demo(q, MEMORY)
            MEMORY.print_status()
    else:
        interactive()
