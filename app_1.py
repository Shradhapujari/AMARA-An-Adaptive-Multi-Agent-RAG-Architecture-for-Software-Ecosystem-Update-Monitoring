"""
Multi-Agent RAG System — Adaptive Multi-Agent RAG Architecture
=============================================
Streamlit web app for software ecosystem monitoring.
Uses 4 live releasetrain.io API endpoints.

Agents:
  0. Temporal Grounder   → rule-based, resolves "today"/"last week" to dates
  1. Community Agent     → reddit/query/positive
  2. Release Notes Agent → /api/v/
  3. CVE Agent           → reddit/query/cve
  4. Query Rewriter      → Llama 3.1 via Ollama (local)
  5. Answer Presenter    → prose paragraph with bracketed evidence
                           (eval_harness provider layer; rule-based offline)

Run:
    pip install streamlit requests
    streamlit run app.py

University of the Pacific — Agentic AI Research — 2026
"""

import streamlit as st
import requests
import json
import urllib.request
import time
from datetime import datetime

from temporal import resolve_temporal, matches_window
from fetch_union import union_fetch, product_terms
from answer_agent import present_answer
from store import open_store, caching_fetch

# ── PAGE CONFIG ──────────────────────────────────────────
st.set_page_config(
    page_title="Multi-Agent RAG System — Software Ecosystem Monitor",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CUSTOM CSS ───────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #0D1B2A 0%, #0E9AA7 100%);
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
    }
    .agent-card {
        background: #f8f9fa;
        border-left: 4px solid #0E9AA7;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .result-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .metric-box {
        background: #0D1B2A;
        color: white;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
    }
    .positive { border-left: 4px solid #2E7D32; }
    .negative { border-left: 4px solid #E8593C; }
    .neutral  { border-left: 4px solid #F5A623; }
    .cve-card { border-left: 4px solid #C62828; background: #FFF5F5; }
    .release-card { border-left: 4px solid #1565C0; background: #F0F4FF; }
</style>
""", unsafe_allow_html=True)

# ── API ENDPOINTS ─────────────────────────────────────────
REDDIT_POSITIVE_API = "https://releasetrain.io/api/reddit/query/positive"
RELEASES_API        = "https://releasetrain.io/api/v/"
CVE_API             = "https://releasetrain.io/api/reddit/query/cve"
OLLAMA_API          = "http://localhost:11434/api/generate"


def presenter_spec() -> str:
    """Which model the Answer Presenter uses, if any.

    Read from Streamlit secrets first so a deployed host can supply one without
    a code change; empty means the presenter runs its rule-based path, which is
    what Community Cloud does today (no Ollama, no key).
    """
    try:
        return str(st.secrets.get("PRESENTER_MODEL", "") or "")
    except Exception:
        return ""

# ── AGENT 1: QUERY REWRITER ──────────────────────────────

def rewrite_query(query: str) -> str:
    """Calls Llama 3.1 locally to rewrite the query for better retrieval."""
    prompt = f"""You are a software update search expert.
Rewrite this query to better match software update documents and Reddit posts.
Focus on: bug fixes, security patches, release notes, CVE vulnerabilities, version updates.
Query: "{query}"
Return ONLY the rewritten query in under 15 words, nothing else:"""

    payload = json.dumps({
        "model": "llama3.1",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0}
    }).encode()

    try:
        req = urllib.request.Request(
            OLLAMA_API,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read()).get("response", "").strip()
            # Llama wraps the rewrite in quotes often enough that the quotes
            # end up in the `q` parameter; strip them rather than search for them.
            return out.strip(" \"'").strip()
    except Exception:
        # Fallback rule-based rewriting
        expansions = {
            "bugs": "bug fixes resolved defects",
            "latest": "latest version release notes",
            "critical": "critical security vulnerability patch",
            "update": "software update release changelog",
            "today": f"released {datetime.now().strftime('%Y-%m-%d')}",
        }
        rewritten = query.lower()
        for k, v in expansions.items():
            if k in rewritten:
                rewritten = rewritten.replace(k, v)
        return rewritten

# ── STORE ────────────────────────────────────────────────
# One SQLite file under data/, opened once per Streamlit process. Two jobs:
# it caches every document the agents retrieve, so a host that cannot reach
# releasetrain.io answers from what earlier runs fetched instead of from an
# "API unavailable" placeholder; and it logs each answered question with the
# documents behind it, so a run is inspectable after the tab is closed.
#
# `cache_resource` and not `cache_data`: the connection is a handle, not a
# value, and re-opening it on every widget interaction would leave a file
# handle per rerun. A store that fails to open is not a reason to refuse the
# question -- the pipeline runs storeless, exactly as it did before.

@st.cache_resource(show_spinner=False)
def get_store():
    try:
        return open_store()
    except Exception:
        return None


# ── AGENT 2: COMMUNITY AGENT ─────────────────────────────

def fetch_community_feedback(query: str, limit: int = 5) -> list:
    """Fetches community Reddit feedback from releasetrain.io."""
    try:
        resp = requests.get(
            REDDIT_POSITIVE_API,
            params={"q": query, "limit": limit},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("data", [])
            return [{
                "title":      p.get("title", ""),
                "subreddit":  p.get("subreddit", ""),
                "url":        p.get("url", ""),
                "score":      p.get("score", 0),
                "sentiment":  "Positive" if p.get("metadata", {}).get("predicted", {}).get("positiveScore", 0) > 0.5 else "Neutral",
                "date":       p.get("created_utc", "")[:10],
                "is_cve":     p.get("isAboutCve", False),
                "is_update":  p.get("isAboutLatestUpdate", False),
            } for p in posts[:limit]]
    except Exception as e:
        return [{"title": f"API unavailable: {e}", "subreddit": "", "url": "", "score": 0, "sentiment": "Neutral", "date": "", "is_cve": False, "is_update": False}]
    return []

# ── AGENT 3: RELEASE NOTES AGENT ─────────────────────────

def fetch_release_notes(query: str, limit: int = 5) -> list:
    """Fetches live software release notes from releasetrain.io."""
    try:
        resp = requests.get(
            RELEASES_API,
            params={"q": query, "limit": limit},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            versions = data.get("versions", [])
            return [{
                "product":   v.get("versionProductName", ""),
                "version":   v.get("versionNumber", ""),
                "date":      v.get("versionReleaseDate", ""),
                "notes":     v.get("versionReleaseNotes", "")[:200],
                "channel":   v.get("versionReleaseChannel", ""),
                "url":       v.get("versionUrl", ""),
                "security":  v.get("classification", {}).get("securityType", []),
                "breaking":  v.get("classification", {}).get("breakingType", []),
                "is_cve":    v.get("isCve", False),
            } for v in versions[:limit]]
    except Exception as e:
        return [{"product": f"API unavailable: {e}", "version": "", "date": "", "notes": "", "channel": "", "url": "", "security": [], "breaking": [], "is_cve": False}]
    return []

# ── AGENT 4: CVE AGENT ───────────────────────────────────

def fetch_cve_data(query: str, limit: int = 5) -> list:
    """Fetches CVE security vulnerability data from releasetrain.io."""
    try:
        resp = requests.get(
            CVE_API,
            params={"q": query, "limit": limit},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("data", [])
            return [{
                "title":     p.get("title", ""),
                "subreddit": p.get("subreddit", ""),
                "url":       p.get("url", ""),
                "date":      p.get("created_utc", "")[:10],
                "score":     p.get("score", 0),
                "tags":      p.get("tags", []),
            } for p in posts[:limit]]
    except Exception as e:
        return [{"title": f"CVE API unavailable: {e}", "subreddit": "", "url": "", "date": "", "score": 0, "tags": []}]
    return []

# ── RLAIF EVALUATOR ──────────────────────────────────────

def evaluate_results(community: list, releases: list, cve: list, query: str) -> dict:
    """Scores result quality and generates RLAIF signal."""
    total   = len(community) + len(releases) + len(cve)
    quality = min(total / 15.0, 1.0)
    signal  = "positive" if quality >= 0.3 else "negative"

    # Count relevant results
    relevant = sum(1 for r in releases if any(
        w in r.get("notes", "").lower() + r.get("product", "").lower()
        for w in query.lower().split()
    ))

    return {
        "quality":        round(quality, 2),
        "signal":         signal,
        "total_results":  total,
        "community_count": len(community),
        "release_count":  len(releases),
        "cve_count":      len(cve),
        "relevant":       relevant,
    }

# ── MANAGER AGENT — ORCHESTRATOR ─────────────────────────

def run_pipeline(query: str, show_steps: bool = True, limit: int = 5) -> dict:
    """Main orchestrator — runs all 4 agents and returns results."""
    results = {
        "original_query":  query,
        "grounded_query":  query,
        "temporal":        None,
        "rewritten_query": "",
        "fetch_phrasings": [],
        "release_phrasings": [],
        "community":       [],
        "releases":        [],
        "cve":             [],
        "evaluation":      {},
        "timing":          {},
    }

    # Step 0 — Temporal Grounder
    # Runs before everything else: retrieval is similarity-based, and no
    # document contains the word "today" -- it contains a date. Resolving the
    # deictic term first means the rewriter, the fetch and the ranker all see
    # the absolute date instead of a token that cannot match.
    t0 = time.time()
    temporal = resolve_temporal(query)
    results["temporal"] = temporal
    results["grounded_query"] = temporal.query
    results["timing"]["temporal"] = round(time.time() - t0, 2)
    grounded = temporal.query

    # Step 1 — Query Rewriter
    if show_steps:
        with st.spinner("🔄 Query Rewriter Agent — Llama 3.1 rewriting query..."):
            t0 = time.time()
            # The rewriter sees the *stripped* phrasing: its job is vocabulary
            # expansion, and handing it the resolved date only gets the date
            # copied into a query that then fetches nothing. The grounded
            # phrasing is fetched alongside it, below.
            rewritten = rewrite_query(temporal.stripped or query)
            results["rewritten_query"] = rewritten
            results["timing"]["rewriter"] = round(time.time()-t0, 1)

    # Fetch phrasings: the expanded one first (recall), then the grounded one
    # (date-aware), deduped so an unchanged query is not fetched twice.
    phrasings = []
    for p in [rewritten or temporal.stripped or query] + temporal.fetch_phrasings:
        if p and p not in phrasings:
            phrasings.append(p)
    results["fetch_phrasings"] = phrasings

    # The release endpoint matches product names, so a sentence retrieves
    # nothing from it however well phrased. Fetch the product term too; the
    # sentence phrasings still run, so nothing they would have found is lost.
    release_phrasings = phrasings + [
        t for t in product_terms(temporal.stripped or query) if t not in phrasings]
    results["release_phrasings"] = release_phrasings

    # Each agent's fetch is wrapped so its results are written to the store and
    # so an unreachable endpoint falls back to the documents earlier runs
    # retrieved. The wrapper is transparent to `union_fetch`, which takes the
    # fetch function as an argument precisely so it can be substituted.
    db = get_store()
    community_fetch = caching_fetch(db, "community", fetch_community_feedback)
    release_fetch   = caching_fetch(db, "release",   fetch_release_notes)
    cve_fetch       = caching_fetch(db, "cve",       fetch_cve_data)

    # Step 2 — Community Agent
    if show_steps:
        with st.spinner("💬 Community Agent — fetching Reddit feedback..."):
            t0 = time.time()
            results["community"] = union_fetch(community_fetch, phrasings, limit, temporal)
            results["timing"]["community"] = round(time.time()-t0, 1)

    # Step 3 — Release Notes Agent
    if show_steps:
        with st.spinner("📦 Release Notes Agent — fetching live releases..."):
            t0 = time.time()
            results["releases"] = union_fetch(release_fetch, release_phrasings,
                                              limit, temporal)
            results["timing"]["releases"] = round(time.time()-t0, 1)

    # Step 4 — CVE Agent
    if show_steps:
        with st.spinner("🔐 CVE Agent — fetching security vulnerabilities..."):
            t0 = time.time()
            results["cve"] = union_fetch(cve_fetch, phrasings, limit, temporal)
            results["timing"]["cve"] = round(time.time()-t0, 1)

    # Step 5 — RLAIF Evaluator
    results["evaluation"] = evaluate_results(
        results["community"], results["releases"],
        results["cve"], grounded
    )

    return results

# ── SIDEBAR ───────────────────────────────────────────────

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/b/bb/University_of_the_Pacific_seal.svg", width=80)
    st.markdown("### Multi-Agent RAG System")
    st.markdown("**Adaptive Multi-Agent RAG Architecture**")
    st.markdown("University of the Pacific · 2026")
    st.divider()

    st.markdown("#### 🤖 Active Agents")
    st.markdown("""
    | Agent | Status |
    |-------|--------|
    | 📅 Temporal Grounder | Rule-based |
    | 🔄 Query Rewriter | Llama 3.1 |
    | 💬 Community | Live API |
    | 📦 Release Notes | Live API |
    | 🔐 CVE Security | Live API |
    | 🧾 Answer Presenter | LLM / rule-based |
    """)
    spec = presenter_spec()
    st.caption(f"Presenter model: `{spec}`" if spec
               else "Presenter model: none configured — cited paragraph is "
                    "composed rule-based.")
    st.divider()

    st.markdown("#### ⚙️ Settings")
    result_limit = st.slider("Results per agent", 3, 10, 5)
    show_pipeline = st.toggle("Show pipeline steps", value=True)
    show_raw = st.toggle("Show raw API data", value=False)

    st.divider()
    st.markdown("#### 💡 Example queries")
    examples = [
        "Any critical Linux updates today?",
        "Security patches released in the past 7 days",
        "Critical software updates published today",
        "What bugs were fixed in Chrome recently?",
        "Any security vulnerabilities in Python?",
        "Latest Django release notes",
        "MacOS updates with negative community reaction",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["query_input"] = ex

    st.divider()
    st.markdown("#### 🗄️ Store")
    _db = get_store()
    if _db is None:
        st.caption("Unavailable — the pipeline runs without it, fetching live "
                   "every time and keeping no history.")
    else:
        _stats = _db.stats()
        sc1, sc2 = st.columns(2)
        sc1.metric("Documents", _stats["documents_total"])
        sc2.metric("Runs", _stats["runs"])
        by_pool = _stats["documents"]
        if by_pool:
            st.caption(" · ".join(f"{k} {v}" for k, v in sorted(by_pool.items())) +
                       (f" · since {(_stats['since'] or '')[:10]}" if _stats["since"] else ""))
        else:
            st.caption("Empty — it fills as questions are asked. Cached documents "
                       "are what answers a question when the API cannot be reached.")

        _recent = _db.recent_runs(limit=8)
        if _recent:
            with st.expander(f"🕘 Last {len(_recent)} question(s)"):
                for r in _recent:
                    flag = " · offline" if r.offline else ""
                    st.markdown(f"**{r.query}**")
                    st.caption(f"{r.ts[:16].replace('T', ' ')} · "
                               f"{r.n_documents} document(s){flag}")
                    if st.button("Ask again", key=f"again_{r.run_id}",
                                 use_container_width=True):
                        st.session_state["query_input"] = r.query

# ── MAIN UI ───────────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h1>🤖 Multi-Agent RAG System — Software Ecosystem Monitor</h1>
    <p>Adaptive Multi-Agent RAG Architecture · University of the Pacific · releasetrain.io</p>
    <p style="font-size:0.9rem; opacity:0.8">
        4 agents · Live APIs · Llama 3.1 · RLAIF feedback · Self-improving
    </p>
</div>
""", unsafe_allow_html=True)

# Query input
query = st.text_input(
    "Ask about any software update, security vulnerability, or release:",
    value=st.session_state.get("query_input", ""),
    placeholder='e.g. "Any critical Linux updates today?" or "What bugs were fixed in Chrome?"',
    key="main_query"
)

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    run_btn = st.button("🚀 Run Multi-Agent Pipeline", type="primary", use_container_width=True)
with col2:
    if st.button("🔁 Clear", use_container_width=True):
        st.session_state["query_input"] = ""
        st.rerun()

# ── PIPELINE EXECUTION ────────────────────────────────────

if run_btn and query:

    # Pipeline steps display
    if show_pipeline:
        st.markdown("---")
        st.markdown("### 🧠 Manager Agent — Think & Plan")
        step_col0, step_col1, step_col2, step_col3, step_col4 = st.columns(5)
        with step_col0:
            st.markdown("""<div class="agent-card">
                <b>Step 0</b><br>📅 Temporal Grounder<br><small>rule-based, offline</small>
            </div>""", unsafe_allow_html=True)
        with step_col1:
            st.markdown("""<div class="agent-card">
                <b>Step 1</b><br>🔄 Query Rewriter<br><small>Llama 3.1 local</small>
            </div>""", unsafe_allow_html=True)
        with step_col2:
            st.markdown("""<div class="agent-card">
                <b>Step 2</b><br>💬 Community Agent<br><small>Reddit Live API</small>
            </div>""", unsafe_allow_html=True)
        with step_col3:
            st.markdown("""<div class="agent-card">
                <b>Step 3</b><br>📦 Release Notes Agent<br><small>Releases Live API</small>
            </div>""", unsafe_allow_html=True)
        with step_col4:
            st.markdown("""<div class="agent-card">
                <b>Step 4</b><br>🔐 CVE Agent<br><small>Security Live API</small>
            </div>""", unsafe_allow_html=True)
        st.markdown("---")

    # Run the pipeline
    results = run_pipeline(query, show_steps=show_pipeline, limit=result_limit)

    # ── TEMPORAL GROUNDING RESULT ─────────────────────────
    tr = results["temporal"]
    st.markdown("### 📅 Temporal Grounder Agent")
    if tr is not None and tr.changed:
        tg1, tg2 = st.columns(2)
        with tg1:
            st.info(f"**As asked:** {tr.original}")
        with tg2:
            st.success(f"**Grounded:** {tr.query}")
        st.caption(f"Resolved {tr.describe()} — relative words are rewritten to "
                   f"absolute dates before retrieval, because no document "
                   f"contains the word “today”, only a date.")
    else:
        st.caption("No relative time expression in this query — nothing to ground. "
                   "(Version words like “latest” are left alone on purpose: they "
                   "are ordinal over releases, not a date.)")

    # ── QUERY REWRITING RESULT ────────────────────────────
    st.markdown("### 🔄 Query Rewriter Agent")
    rw_col1, rw_col2 = st.columns(2)
    with rw_col1:
        st.info(f"**Grounded input:** {results['grounded_query']}")
    with rw_col2:
        st.success(f"**Rewritten:** {results['rewritten_query'] or results['original_query']}")
    fetched_on = results.get("release_phrasings") or results.get("fetch_phrasings", [])
    if len(fetched_on) > 1:
        st.caption("Fetched on every phrasing and unioned — " +
                   " · ".join(f"“{p}”" for p in fetched_on) +
                   ". The plain phrasing and the product term find the documents; "
                   "the dated one lets the window rank them.")

    # ── RLAIF EVALUATION METRICS ──────────────────────────
    st.markdown("### 📊 RLAIF Evaluator")
    ev = results["evaluation"]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Quality Score", f"{ev['quality']:.2f}/1.0")
    m2.metric("RLAIF Signal", "✅ Positive" if ev["signal"]=="positive" else "⚠️ Retry")
    m3.metric("Community Posts", ev["community_count"])
    m4.metric("Release Notes", ev["release_count"])
    m5.metric("CVE Results", ev["cve_count"])

    timing = results["timing"]
    st.caption(f"⏱ Timing — Temporal: {timing.get('temporal',0)}s | Rewriter: {timing.get('rewriter',0)}s | Community: {timing.get('community',0)}s | Releases: {timing.get('releases',0)}s | CVE: {timing.get('cve',0)}s")

    st.markdown("---")

    # ── RESULTS TABS ──────────────────────────────────────
    tab1, tab2, tab3 = st.tabs([
        f"📦 Release Notes ({len(results['releases'])})",
        f"💬 Community Feedback ({len(results['community'])})",
        f"🔐 CVE Security ({len(results['cve'])})",
    ])

    # Release Notes Tab
    with tab1:
        st.markdown("**Live software releases from releasetrain.io/api/v/**")
        if tr is not None and tr.window and results["releases"]:
            inside = sum(1 for r in results["releases"]
                         if matches_window(r.get("date", ""), tr) is True)
            st.caption(f"{inside} of {len(results['releases'])} shown releases fall "
                       f"inside {tr.window[0]} … {tr.window[1]}. Out-of-window results "
                       f"are kept and ranked last rather than dropped, so a quiet day "
                       f"still returns something to read.")
        if results["releases"]:
            for r in results["releases"]:
                is_security = "SECURITY" in r.get("security", [])
                has_breaking = len(r.get("breaking", [])) > 0
                badge = "🔴 SECURITY" if is_security else ("🟡 BREAKING" if has_breaking else "🟢 UPDATE")
                # Whether this release actually falls in the asked-about window.
                # None = no window asked for, or an unparseable date: shown as
                # nothing rather than as a miss.
                in_win = matches_window(r.get("date", ""), tr) if tr is not None else None
                win_badge = "" if in_win is None else (" 📅 in window" if in_win else " ⏳ outside window")

                with st.expander(f"{badge} {r['product']} v{r['version']} — {r['date']}{win_badge}"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**Release Notes:** {r['notes'] or 'No notes available'}")
                        if r.get("breaking"):
                            st.warning(f"⚠️ Breaking changes: {', '.join(r['breaking'])}")
                        if r.get("security") and r["security"] != ["UNKNOWN"]:
                            st.error(f"🔐 Security type: {', '.join(r['security'])}")
                    with col2:
                        st.markdown(f"**Channel:** {r['channel']}")
                        if r.get("url"):
                            st.markdown(f"[View on GitHub]({r['url']})")
        else:
            st.info("No release notes found for this query.")

    # Community Feedback Tab
    with tab2:
        st.markdown("**Live Reddit community feedback from releasetrain.io**")
        if results["community"]:
            for post in results["community"]:
                sentiment_class = "positive" if post["sentiment"]=="Positive" else "negative" if post["sentiment"]=="Negative" else "neutral"
                icon = "🟢" if post["sentiment"]=="Positive" else "🔴" if post["sentiment"]=="Negative" else "🟡"

                with st.expander(f"{icon} {post['title'][:80]}"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Subreddit", f"r/{post['subreddit']}")
                    col2.metric("Score", post["score"])
                    col3.metric("Date", post["date"])

                    tags = []
                    if post.get("is_cve"): tags.append("🔐 CVE")
                    if post.get("is_update"): tags.append("📦 Update")
                    if tags: st.markdown(" ".join(tags))
                    if post.get("url"): st.markdown(f"[View on Reddit]({post['url']})")
        else:
            st.info("No community feedback found for this query.")

    # CVE Tab
    with tab3:
        st.markdown("**Security vulnerabilities from releasetrain.io CVE feed**")
        if results["cve"]:
            for cve in results["cve"]:
                with st.expander(f"🔐 {cve['title'][:80]}"):
                    col1, col2 = st.columns(2)
                    col1.metric("Subreddit", f"r/{cve['subreddit']}")
                    col2.metric("Date", cve["date"])
                    if cve.get("tags"): st.markdown(f"**Tags:** {', '.join(cve['tags'])}")
                    if cve.get("url"): st.markdown(f"[View post]({cve['url']})")
        else:
            st.info("No CVE results found. Try adding 'CVE' or a specific version to your query.")

    # Raw data
    if show_raw:
        with st.expander("🔍 Raw API response data"):
            # `temporal` holds a dataclass, which st.json cannot serialise;
            # show its resolved fields instead of dropping the step from view.
            raw = dict(results)
            raw["temporal"] = {
                "original": tr.original, "grounded": tr.query,
                "resolved": [{"matched": a, "as": b} for a, b in tr.terms],
                "window": [str(tr.start), str(tr.end)] if tr.window else None,
            } if tr is not None else None
            st.json(raw)

    # ── FINAL GROUNDED ANSWER ─────────────────────────────
    # The Answer Presenter agent turns the retrieved documents into one
    # readable paragraph and cites each claim in brackets. It reuses the
    # eval harness's provider layer, so the presenting model is configurable
    # (PRESENTER_MODEL in Streamlit secrets or the environment); with no model
    # reachable it composes the same shape by rule and says so, rather than
    # dressing rule-based text up as model output.
    st.markdown("---")
    st.markdown("### ✅ Final Answer")

    window_note = ""
    if tr is not None and tr.window:
        a, b = tr.window
        window_note = (a.strftime("%b %d, %Y") if a == b
                       else f'{a.strftime("%b %d, %Y")} to {b.strftime("%b %d, %Y")}')

    with st.spinner("🧾 Answer Presenter Agent — writing a cited paragraph..."):
        t0 = time.time()
        presented = present_answer(
            results["original_query"], results,
            model_spec=presenter_spec(), window_note=window_note,
            per_kind=result_limit,
        )
        present_secs = round(time.time() - t0, 1)

    st.success(presented.text)

    src_label = (f"Presented by {presented.model}" if presented.mode == "llm"
                 else f"Presented rule-based ({presented.note})")
    st.caption(f"{src_label} · {len(presented.evidence)} evidence item(s) cited · {present_secs}s")

    if presented.evidence:
        with st.expander("🔗 Evidence behind the bracketed citations"):
            for e in presented.evidence:
                line = f"**[{e.label}]** — {e.title}"
                if e.url:
                    line += f" · [open source]({e.url})"
                st.markdown(line)

    # ── LOG THE RUN ───────────────────────────────────────
    # Written after the answer exists, so the stored row is the whole run --
    # question, phrasings, retrieved documents in rank order, and which of them
    # the answer actually cited. `record_run` swallows its own failures and
    # returns None; a store that cannot write must not cost the user an answer
    # already on screen.
    #
    # A run is marked offline when any shown document came from the store
    # rather than the endpoint. Cache-served rows carry `_last_seen`, which a
    # freshly fetched row does not, so the flag is read off the documents
    # instead of guessed from an exception that never reached this scope.
    _db_run = get_store()
    if _db_run is not None:
        _served = (results["releases"] + results["community"] + results["cve"])
        _offline = any("_last_seen" in d for d in _served if isinstance(d, dict))
        _run_id = _db_run.record_run(
            dict(results,
                 cited_keys=[e.url for e in presented.evidence if e.url]),
            answer=presented.text, offline=_offline)
        if _offline:
            st.warning("Some sources were unreachable — the documents above "
                       "were served from the local store, retrieved during an "
                       "earlier run. Dates on them are release dates, not "
                       "retrieval dates.")
        if _run_id is not None:
            st.caption(f"Logged as run #{_run_id} in the local store.")

elif run_btn and not query:
    st.warning("Please enter a query first.")

# ── FOOTER ────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center; color:#888; font-size:0.85rem;">
    Multi-Agent RAG System · Adaptive Multi-Agent RAG Architecture · University of the Pacific · 2026<br>
    Shradha Devendra Pujari · Dr. Solomon Berhe · releasetrain.io
</div>
""", unsafe_allow_html=True)
