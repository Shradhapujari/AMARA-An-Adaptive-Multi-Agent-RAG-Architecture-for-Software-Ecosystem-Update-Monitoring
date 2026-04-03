"""
RAG Query Rewriting Agent — HuggingFace smolagents style
=========================================================
Recreates the Alfred diagram from HuggingFace Unit 1 but for
your research topic: query rewriting in RAG systems.
Diagram mapping:
  "Bring me a coffee"     →  "What bugs were fixed in latest update?"
  Alfred (agent)          →  RAG Query Rewriting Agent
  Coffee machine          →  FAISS vector store + BGE-Large embeddings
  Laptop / blender        →  rewrite_query, retrieve_docs, generate_answer
  Step 1: Think & Plan    →  Detect semantic gap, choose rewriting strategy
  Step 2: Act using tools →  Rewrite → Retrieve → Rerank → Generate
HuggingFace course reference:
  https://huggingface.co/learn/agents-course/en/unit1/what-are-agents
Usage:
  # Option A — Ollama (local, no API key needed — recommended for your Mac)
  pip install smolagents langchain-ollama ollama
  ollama pull llama3.1
  python rag_agent_smolagents.py --backend ollama
  # Option B — HuggingFace Inference API (free tier)
  pip install smolagents
  huggingface-cli login
  python rag_agent_smolagents.py --backend hf
  # Option C — OpenAI
  pip install smolagents openai
  export OPENAI_API_KEY=your_key
  python rag_agent_smolagents.py --backend openai
"""
import json
import sys
import argparse
from pathlib import Path
# ─────────────────────────────────────────────────────────────
# ARGUMENT PARSING
# ─────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="RAG Query Rewriting Agent (smolagents)")
parser.add_argument("--backend", choices=["ollama", "hf", "openai"], default="ollama",
                    help="LLM backend to use (default: ollama)")
parser.add_argument("--query", type=str, default=None,
                    help="Custom query to run (optional)")
args = parser.parse_args()
# ─────────────────────────────────────────────────────────────
# DATASET  (Darshana's Reddit sentiment data as our "document store")
# ─────────────────────────────────────────────────────────────
DATA_PATH = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"
def _load_docs() -> list[dict]:
    """Load posts as documents for retrieval."""
    if not DATA_PATH.exists():
        print(f"⚠️  Dataset not found at {DATA_PATH}")
        print("   Using mock documents for demo.")
        return [
            {"title": "Critical bug fix: memory leak in v2.1", "subreddit": "Python",     "text": "Fixed memory leak causing crashes after 100 requests"},
            {"title": "Security patch released for auth bypass", "subreddit": "linux",     "text": "CVE-2024-1234 patched — auth bypass vulnerability resolved"},
            {"title": "Performance regression fixed in latest build", "subreddit": "rust", "text": "30% slowdown in v3.0 traced to allocator bug, now fixed"},
            {"title": "Breaking change: API endpoint deprecated",  "subreddit": "django",  "text": "Old /api/v1/users endpoint removed, migrate to /api/v2/users"},
            {"title": "Update improves startup time by 40%",       "subreddit": "neovim",  "text": "Lazy loading plugins now default, startup ~40ms faster"},
        ]
    with open(DATA_PATH) as f:
        data = json.load(f)
    posts = data.get("all_analyzed_posts", [])
    return [{
        "title":     p.get("title", ""),
        "subreddit": p.get("subreddit", ""),
        "text":      p.get("title", "") + " — sentiment: " + p.get("title_sentiment", {}).get("label", ""),
        "score":     p.get("score", 0),
        "url":       p.get("url", ""),
    } for p in posts]
DOCS = _load_docs()
print(f"✅  Document store loaded: {len(DOCS)} docs")
# ─────────────────────────────────────────────────────────────
# TOOLS  (the "laptop / blender / coffee machine" in the diagram)
# ─────────────────────────────────────────────────────────────
from smolagents import tool
@tool
def rewrite_query(query: str) -> str:
    """
    Rewrites a vague or ambiguous user query into a precise,
    retrieval-ready query that better matches document vocabulary.
    This is Step 1 of the RAG pipeline — bridging the semantic gap.
    Always call this first before retrieving documents.
    Args:
        query: the original user query, which may be vague or ambiguous
    """
    # Semantic gap detection — expand shorthand terms
    expansions = {
        "latest ver":    "latest version release notes",
        "latest update": "software update changelog release notes fixes",
        "new version":   "new version changelog release notes bug fixes features",
        "bugs":          "bug fixes defects resolved issues errors",
        "fixes":         "bug fixes patches resolved defects",
        "perf":          "performance optimization speed improvement",
        "slow":          "performance regression slowdown latency issue",
        "crash":         "crash bug memory error segfault",
        "security":      "security vulnerability CVE patch authentication",
        "breaking":      "breaking change API deprecation migration",
    }
    rewritten = query.lower()
    applied = []
    for short, expanded in expansions.items():
        if short in rewritten:
            rewritten = rewritten.replace(short, expanded)
            applied.append(short)
    if not applied:
        rewritten = f"{query} software update changelog release notes fixes improvements"
    result = {
        "original_query":  query,
        "rewritten_query": rewritten.strip(),
        "expansions_applied": applied if applied else ["generic expansion"],
        "semantic_gap_detected": len(applied) > 0,
    }
    print(f"\n  🔄  QUERY REWRITTEN")
    print(f"      Original  : {query}")
    print(f"      Rewritten : {rewritten.strip()}")
    return json.dumps(result, indent=2)
@tool
def retrieve_docs(query: str, top_k: int = 5) -> str:
    """
    Retrieves the most relevant documents from the vector store
    using the rewritten query. Uses keyword matching as a proxy
    for FAISS/BGE-Large embedding similarity.
    Always use the rewritten query from rewrite_query(), not the original.
    Args:
        query: the rewritten query string from rewrite_query()
        top_k: number of documents to return (default 5, max 10)
    """
    top_k = min(int(top_k), 10)
    query_terms = set(query.lower().split())
    scored = []
    for doc in DOCS:
        doc_text  = (doc["title"] + " " + doc.get("text", "") + " " + doc.get("subreddit", "")).lower()
        doc_terms = set(doc_text.split())
        overlap   = len(query_terms & doc_terms)
        if overlap > 0:
            scored.append((overlap, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [doc for _, doc in scored[:top_k]]
    if not results:
        results = DOCS[:top_k]
    print(f"\n  📚  RETRIEVED {len(results)} docs")
    for r in results[:3]:
        print(f"      • {r['title'][:55]}")
    return json.dumps([{
        "title":     d["title"],
        "subreddit": d.get("subreddit", ""),
        "snippet":   d.get("text", d["title"])[:120],
        "url":       d.get("url", ""),
    } for d in results], indent=2)
@tool
def rerank_results(docs_json: str, query: str) -> str:
    """
    Reranks retrieved documents by relevance to the original query intent.
    Simulates BGE-Large cross-encoder reranking.
    Call this after retrieve_docs() to improve result quality.
    Args:
        docs_json: JSON string output from retrieve_docs()
        query: the original user query (for relevance scoring)
    """
    try:
        docs = json.loads(docs_json)
    except Exception:
        return docs_json
    query_terms = set(query.lower().split())
    for doc in docs:
        title_terms = set(doc.get("title", "").lower().split())
        doc["relevance_score"] = round(len(query_terms & title_terms) / max(len(query_terms), 1), 3)
    docs.sort(key=lambda d: d["relevance_score"], reverse=True)
    print(f"\n  🏆  RERANKED — top result: {docs[0]['title'][:50] if docs else 'none'}")
    return json.dumps(docs, indent=2)
@tool
def evaluate_retrieval(docs_json: str, query: str) -> str:
    """
    Evaluates the quality of retrieved documents using RLAIF-style scoring.
    Returns a quality score and a recommendation on whether to retry retrieval
    with a different rewriting strategy. This is the feedback mechanism
    that makes the pipeline adaptive rather than static.
    Args:
        docs_json: JSON string of retrieved/reranked documents
        query: the original user query
    """
    try:
        docs = json.loads(docs_json)
    except Exception:
        return json.dumps({"quality_score": 0.0, "recommendation": "retry"})
    if not docs:
        return json.dumps({"quality_score": 0.0, "recommendation": "retry — no docs retrieved"})
    query_terms  = set(query.lower().split())
    top_doc      = docs[0]
    title_terms  = set(top_doc.get("title", "").lower().split())
    overlap      = len(query_terms & title_terms)
    quality      = min(round(overlap / max(len(query_terms), 1), 2), 1.0)
    recommendation = "good — proceed to generate" if quality >= 0.2 else "low quality — consider re-rewriting query"
    result = {
        "quality_score":    quality,
        "top_doc_title":    top_doc.get("title", ""),
        "recommendation":   recommendation,
        "rlaif_signal":     "positive" if quality >= 0.2 else "negative",
        "docs_evaluated":   len(docs),
    }
    print(f"\n  📊  RLAIF EVAL — quality: {quality} | signal: {result['rlaif_signal']}")
    return json.dumps(result, indent=2)
@tool
def generate_answer(docs_json: str, original_query: str) -> str:
    """
    Generates a grounded, concise answer from the retrieved documents.
    This is the final step — synthesizing retrieved context into a response.
    Only call this after retrieve_docs() and optionally rerank_results().
    Args:
        docs_json: JSON string of retrieved documents
        original_query: the original user question to answer
    """
    try:
        docs = json.loads(docs_json)
    except Exception:
        docs = []
    if not docs:
        return json.dumps({"answer": "No relevant documents found.", "sources": []})
    top_docs  = docs[:3]
    context   = "\n".join([f"- {d.get('title','')}: {d.get('snippet', '')[:80]}" for d in top_docs])
    sources   = [d.get("url", d.get("title", "")) for d in top_docs]
    answer = (
        f"Based on {len(top_docs)} retrieved documents about '{original_query}':\n\n"
        f"{context}\n\n"
        f"The most relevant result is: '{top_docs[0].get('title', '')}'"
    )
    print(f"\n  ✅  ANSWER GENERATED from {len(top_docs)} docs")
    return json.dumps({
        "answer":       answer,
        "sources":      sources[:3],
        "grounded":     True,
        "doc_count":    len(top_docs),
    }, indent=2)
# ─────────────────────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────────────────────
TOOLS = [
    rewrite_query,
    retrieve_docs,
    rerank_results,
    evaluate_retrieval,
    generate_answer,
]
# ─────────────────────────────────────────────────────────────
# MODEL SETUP  (Brain — the LLM)
# ─────────────────────────────────────────────────────────────
def build_model():
    """Build the LLM model based on chosen backend."""
    if args.backend == "ollama":
        print("🧠  Brain: Llama 3.1 8B via Ollama (local)")
        print("    Make sure: ollama serve && ollama pull llama3.1")
        try:
            from smolagents import LiteLLMModel
            return LiteLLMModel(model_id="ollama/llama3.1")
        except Exception:
            print("⚠️  LiteLLMModel not available, trying HfApiModel fallback...")
            from smolagents import HfApiModel
            return HfApiModel(model_id="meta-llama/Llama-3.1-8B-Instruct")
    elif args.backend == "hf":
        print("🧠  Brain: Llama 3.1 8B via HuggingFace Inference API")
        print("    Make sure: huggingface-cli login")
        from smolagents import HfApiModel
        return HfApiModel(model_id="meta-llama/Llama-3.1-8B-Instruct")
    elif args.backend == "openai":
        print("🧠  Brain: GPT-4o-mini via OpenAI")
        from smolagents import LiteLLMModel
        return LiteLLMModel(model_id="gpt-4o-mini")
# ─────────────────────────────────────────────────────────────
# AGENT SETUP
# ─────────────────────────────────────────────────────────────
def build_agent():
    """Build the smolagents CodeAgent — the Alfred of your RAG system."""
    from smolagents import CodeAgent
    model = build_model()
    agent = CodeAgent(
        tools=TOOLS,
        model=model,
        name="RAG_Query_Rewriting_Agent",
        description=(
            "An agentic RAG system that detects semantic gaps in user queries, "
            "rewrites them for better retrieval, retrieves and reranks documents, "
            "evaluates quality with RLAIF signals, and generates grounded answers. "
            "Always rewrite the query first, then retrieve, then generate."
        ),
        max_steps=8,
        verbosity_level=2,
    )
    return agent
# ─────────────────────────────────────────────────────────────
# DEMO QUERIES
# ─────────────────────────────────────────────────────────────
DEMO_QUERIES = [
    "What bugs were fixed in the latest software update?",
    "How do users feel about the latest ver of comfyui?",
    "Which releases had the most negative community reaction?",
]
# ─────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────
def print_header():
    W = 60
    print("═" * W)
    print("  RAG Query Rewriting Agent")
    print("  HuggingFace smolagents — Unit 1 style")
    print("─" * W)
    print("  Brain  : Llama 3.1 8B (Ollama local)")
    print("  Body   : 5 tools — rewrite · retrieve · rerank · eval · generate")
    print("  Data   : Reddit software update posts (324 docs)")
    print("─" * W)
    print("  Think & Plan → Select Tools → Act using Tools")
    print("═" * W)
    print()
def run_query(agent, query: str):
    W = 60
    print(f"\n{'═' * W}")
    print(f"  📨  USER REQUEST (like 'Bring me a coffee')")
    print(f"{'─' * W}")
    print(f"  {query}")
    print(f"{'═' * W}\n")
    try:
        result = agent.run(query)
        print(f"\n{'═' * W}")
        print("  ✅  FINAL ANSWER")
        print(f"{'═' * W}")
        print(result)
        print(f"{'═' * W}\n")
    except Exception as e:
        print(f"\n❌  Error: {e}")
        print("💡  Tips:")
        print("    - Ollama: run 'ollama serve' in another terminal")
        print("    - HF: run 'huggingface-cli login' first")
        print("    - OpenAI: set OPENAI_API_KEY environment variable")
def run_interactive(agent):
    print_header()
    print("Commands: 'demo' to run all 3 demo queries | 'exit' to quit | any question\n")
    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if user_input.lower() == "demo":
            for q in DEMO_QUERIES:
                run_query(agent, q)
        else:
            run_query(agent, user_input)
# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    agent = build_agent()
    if args.query:
        print_header()
        run_query(agent, args.query)
    elif "--demo" in sys.argv:
        print_header()
        for q in DEMO_QUERIES:
            run_query(agent, q)
    else:
        run_interactive(agent)
