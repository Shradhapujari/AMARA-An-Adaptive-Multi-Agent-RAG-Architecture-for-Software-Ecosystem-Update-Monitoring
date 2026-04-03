"""
Multi-Agent Demo: LangChain Agent + Sentiment Tool
===================================================
Connects to Darshana's enhanced_automated_sentiment_results.json
and answers natural language queries about Reddit sentiment data.

Usage:
    python demo_main.py

Requirements:
    pip install langchain langchain-core langchain-ollama ollama python-dotenv
    ollama pull llama3.1
"""

import json
import os
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain.tools import tool
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

# Update this path to wherever your local copy of the dataset lives
DATA_PATH = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"

LLM_MODEL  = "llama3.1"   # or "mistral" — both work via Ollama
TEMPERATURE = 0            # deterministic outputs for demos


# ─────────────────────────────────────────────────────────────
# DATA LOADER  (loads once, stays in memory)
# ─────────────────────────────────────────────────────────────

def _load_data() -> dict:
    """Load Darshana's sentiment dataset. Falls back gracefully if missing."""
    if not DATA_PATH.exists():
        print(f"⚠️  Dataset not found at {DATA_PATH}")
        print("    Place enhanced_automated_sentiment_results.json in ./data/")
        return {}
    with open(DATA_PATH) as f:
        return json.load(f)

_SENTIMENT_DATA = _load_data()
_ALL_POSTS: list[dict] = _SENTIMENT_DATA.get("all_analyzed_posts", [])


# ─────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────

@tool
def get_sentiment_overview() -> str:
    """
    Returns a high-level overview of the entire Reddit sentiment dataset —
    total posts analyzed, sentiment model used, and filtering criteria.
    Use this when the user asks for a general summary of the dataset.
    """
    if not _SENTIMENT_DATA:
        return "Dataset not loaded. Check DATA_PATH in demo_main.py."

    meta = _SENTIMENT_DATA.get("analysis_metadata", {})
    return json.dumps({
        "total_posts_fetched":   meta.get("total_posts_fetched"),
        "total_posts_analyzed":  meta.get("total_posts_analyzed"),
        "sentiment_model":       meta.get("sentiment_model"),
        "analysis_date":         meta.get("date"),
        "filtering_criteria":    meta.get("enhanced_filtering"),
    }, indent=2)


@tool
def get_highest_divergence_posts(top_n: str = "5") -> str:
    """
    Returns the posts with the highest author-community sentiment divergence.
    Divergence measures how differently the post author and the community
    responded emotionally to the same thread.
    Use this when asked: 'which posts have the biggest gap between author and community sentiment'.
    Args:
        top_n: Number of top posts to return (default 5, max 10). Pass just the number, e.g. 5
    """
    if not _ALL_POSTS:
        return "Dataset not loaded."

    # Strip any extra text the LLM may have included (e.g. "top_n=5 (default value)")
    import re
    match = re.search(r'\d+', str(top_n))
    top_n = min(int(match.group()) if match else 5, 10)
    sorted_posts = sorted(
        _ALL_POSTS,
        key=lambda p: p.get("metrics", {}).get("sentiment_divergence", 0),
        reverse=True
    )[:top_n]

    result = []
    for p in sorted_posts:
        m = p.get("metrics", {})
        result.append({
            "title":               p.get("title"),
            "subreddit":           p.get("subreddit"),
            "sentiment_divergence": round(m.get("sentiment_divergence", 0), 3),
            "author_avg_sentiment": round(m.get("author_avg_sentiment", 0), 3),
            "community_avg_sentiment": round(m.get("community_avg_sentiment", 0), 3),
            "url":                 p.get("url"),
        })
    return json.dumps(result, indent=2)


@tool
def get_sentiment_by_subreddit() -> str:
    """
    Groups posts by subreddit and returns the average community sentiment
    for each subreddit, sorted from most negative to most positive.
    Use this when asked about sentiment by community, subreddit, or platform.
    """
    if not _ALL_POSTS:
        return "Dataset not loaded."

    subreddit_stats: dict[str, list[float]] = {}
    for post in _ALL_POSTS:
        subreddit = post.get("subreddit", "unknown")
        community_sentiment = post.get("metrics", {}).get("community_avg_sentiment", 0)
        subreddit_stats.setdefault(subreddit, []).append(community_sentiment)

    # Compute averages and sort
    summary = []
    for sub, scores in subreddit_stats.items():
        avg = round(sum(scores) / len(scores), 3)
        summary.append({
            "subreddit":          sub,
            "avg_community_sentiment": avg,
            "post_count":         len(scores),
            "sentiment_label":    "positive" if avg >= 0.05 else ("negative" if avg <= -0.05 else "neutral")
        })
    summary.sort(key=lambda x: x["avg_community_sentiment"])

    return json.dumps(summary, indent=2)


@tool
def get_defect_vs_usability_sentiment() -> str:
    """
    Compares sentiment metrics between software defect posts and usability posts.
    Returns average author sentiment, community sentiment, and divergence for each category.
    Use this when asked to compare defect vs usability posts, or when asked about
    sentiment trends for a specific post type.
    """
    if not _ALL_POSTS:
        return "Dataset not loaded."

    # Classify by keywords in title (matches Darshana's categorization approach)
    defect_keywords    = ["fix", "bug", "error", "issue", "broken", "crash", "fail", "defect", "problem"]
    usability_keywords = ["update", "new", "release", "feature", "improve", "upgrade", "version", "launch"]

    defect_posts    = []
    usability_posts = []

    for post in _ALL_POSTS:
        title_lower = post.get("title", "").lower()
        metrics     = post.get("metrics", {})

        is_defect    = any(kw in title_lower for kw in defect_keywords)
        is_usability = any(kw in title_lower for kw in usability_keywords)

        entry = {
            "author_sentiment":    metrics.get("author_avg_sentiment", 0),
            "community_sentiment": metrics.get("community_avg_sentiment", 0),
            "divergence":          metrics.get("sentiment_divergence", 0),
        }
        if is_defect:
            defect_posts.append(entry)
        if is_usability:
            usability_posts.append(entry)

    def avg_metrics(posts):
        if not posts:
            return {"post_count": 0}
        return {
            "post_count":                len(posts),
            "avg_author_sentiment":      round(sum(p["author_sentiment"]    for p in posts) / len(posts), 3),
            "avg_community_sentiment":   round(sum(p["community_sentiment"] for p in posts) / len(posts), 3),
            "avg_divergence":            round(sum(p["divergence"]          for p in posts) / len(posts), 3),
        }

    return json.dumps({
        "software_defect_posts": avg_metrics(defect_posts),
        "usability_posts":       avg_metrics(usability_posts),
        "interpretation": (
            "Higher divergence = author and community reacted differently. "
            "Negative avg_author_sentiment = author was frustrated. "
            "Positive avg_community_sentiment = community was helpful/supportive."
        )
    }, indent=2)


@tool
def get_post_by_id(post_id: str) -> str:
    """
    Returns full sentiment details for a specific Reddit post by its post ID.
    Use this when the user asks about a specific post or wants to drill into one result.
    Args:
        post_id: The Reddit post ID (e.g. '1o094i5')
    """
    if not _ALL_POSTS:
        return "Dataset not loaded."

    for post in _ALL_POSTS:
        if post.get("post_id") == post_id:
            return json.dumps({
                "post_id":         post.get("post_id"),
                "title":           post.get("title"),
                "subreddit":       post.get("subreddit"),
                "url":             post.get("url"),
                "score":           post.get("score"),
                "num_comments":    post.get("num_comments"),
                "title_sentiment": post.get("title_sentiment"),
                "metrics":         post.get("metrics"),
            }, indent=2)

    return f"Post with ID '{post_id}' not found in the dataset."


# ─────────────────────────────────────────────────────────────
# AGENT SETUP
# ─────────────────────────────────────────────────────────────

TOOLS = [
    get_sentiment_overview,
    get_highest_divergence_posts,
    
    
    get_post_by_id,
]

# ReAct prompt — tells the agent how to think step by step
REACT_PROMPT = PromptTemplate.from_template("""
You are an expert AI research assistant analyzing Reddit sentiment data about software updates.
You have access to a dataset of {total_posts} Reddit posts analyzed using VADER sentiment analysis.
Always use the available tools to answer questions — never guess or make up data.
Return clear, concise answers in plain English after analyzing the tool output.

Available tools:
{tools}

Tool names: {tool_names}

Use this format EXACTLY — do not deviate:

Question: the input question you must answer
Thought: think about which tool to use and why
Action: the tool name to call
Action Input: the input to the tool (a single value only, no extra text)
Observation: the result of the tool
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now have enough information to answer
Final Answer: your plain-English answer based on the data

IMPORTANT: Every response MUST end with "Final Answer:" followed by your answer.
Never stop after an Observation — always follow up with a Thought and then Final Answer.

Begin!

Question: {input}
Thought: {agent_scratchpad}
""")

llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)

agent = create_react_agent(
    llm=llm,
    tools=TOOLS,
    prompt=REACT_PROMPT.partial(total_posts=len(_ALL_POSTS)),
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=TOOLS,
    verbose=True,           # Shows reasoning steps — great for a demo
    handle_parsing_errors=True,
    max_iterations=10,
)


# ─────────────────────────────────────────────────────────────
# DEMO QUERIES  (the 3 from slide 8)
# ─────────────────────────────────────────────────────────────

DEMO_QUERIES = [
    "Which posts have the highest author-community sentiment divergence?",
    "Summarize sentiment trends for software defect posts",
    "What subreddits show the most negative community reaction?",
]


def run_query(question: str) -> str:
    """Run a single query through the agent and return the final answer."""
    print("\n" + "═" * 60)
    print(f"❓ QUERY: {question}")
    print("═" * 60)
    try:
        result = agent_executor.invoke({"input": question})
        answer = result.get("output", "No answer returned.")
        print(f"\n✅ FINAL ANSWER:\n{answer}")
        return answer
    except Exception as e:
        error_msg = f"Agent error: {e}"
        print(f"❌ {error_msg}")
        return error_msg


def run_interactive():
    """Interactive REPL — type any question, 'demo' to run all 3, 'exit' to quit."""
    print("\n" + "═" * 60)
    print("  🤖  LangChain Sentiment Agent  —  releasetrain.io")
    print(f"  📊  Dataset: {len(_ALL_POSTS)} posts loaded")
    print("  💡  Type a question, 'demo' to run demo queries, or 'exit' to quit")
    print("═" * 60)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break
        if user_input.lower() == "demo":
            for q in DEMO_QUERIES:
                run_query(q)
        else:
            run_query(user_input)


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Run a specific demo query if passed as argument
    # e.g. python demo_main.py "Which subreddits are most negative?"
    if len(sys.argv) > 1:
        run_query(" ".join(sys.argv[1:]))
    else:
        run_interactive()