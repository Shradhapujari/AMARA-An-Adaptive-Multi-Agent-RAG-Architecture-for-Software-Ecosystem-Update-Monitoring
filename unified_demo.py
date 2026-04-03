"""
Unified Multi-Agent Demo
========================
Runs the SAME query through 3 frameworks side by side.
Run: python unified_demo.py
Type 'compare' or 'demo' or any question
"""

import json, time, sys, urllib.request
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "enhanced_automated_sentiment_results.json"

def load_docs():
    if DATA_PATH.exists():
        with open(DATA_PATH) as f:
            posts = json.load(f).get("all_analyzed_posts", [])
        return [{"title":p["title"],"subreddit":p["subreddit"],
                 "sentiment":p["title_sentiment"]["label"],
                 "divergence":p["metrics"]["sentiment_divergence"],
                 "url":p.get("url","")} for p in posts]
    return [
        {"title":"Critical bug fix: memory leak in Python 3.11","subreddit":"Python","sentiment":"Negative","divergence":0.3,"url":""},
        {"title":"Security patch for auth bypass","subreddit":"linux","sentiment":"Negative","divergence":0.5,"url":""},
        {"title":"Comfyui v2.1 breaks all custom nodes","subreddit":"comfyui","sentiment":"Negative","divergence":0.6,"url":""},
        {"title":"Rust 1.75 massive performance improvements","subreddit":"rust","sentiment":"Positive","divergence":0.1,"url":""},
        {"title":"WordPress 6.4 update causes white screen","subreddit":"Wordpress","sentiment":"Negative","divergence":0.4,"url":""},
        {"title":"Neovim 0.10 is incredibly fast now","subreddit":"neovim","sentiment":"Positive","divergence":0.2,"url":""},
        {"title":"Django 5.0 deprecates old middleware","subreddit":"django","sentiment":"Neutral","divergence":0.3,"url":""},
        {"title":"VSCode update broke Python debugger","subreddit":"vscode","sentiment":"Negative","divergence":0.5,"url":""},
    ]

DOCS = load_docs()
W = 62

def bar(c="─"): print(c * W)
def pause(s=0.5): time.sleep(s)

def search_docs(query, top_k=4):
    terms = set(query.lower().split())
    scored = sorted([(len(terms & set((d["title"]+" "+d["subreddit"]).lower().split())),d) for d in DOCS],key=lambda x:x[0],reverse=True)
    return [d for s,d in scored if s>0][:top_k] or DOCS[:top_k]

def call_llama(prompt):
    payload = json.dumps({"model":"llama3.1","prompt":prompt,"stream":False,"options":{"temperature":0}}).encode()
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate",data=payload,headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=30) as r:
            return json.loads(r.read()).get("response","").strip()
    except Exception as e:
        return f"[Ollama unavailable]"

def build_answer(docs, query):
    neg = [d for d in docs if d["sentiment"]=="Negative"]
    pos = [d for d in docs if d["sentiment"]=="Positive"]
    subs = list(set(d["subreddit"] for d in docs))
    lines = [f'Answer for: "{query}"\n']
    if neg:
        lines.append(f"  Issues found ({len(neg)} posts):")
        for d in neg: lines.append(f"    - {d['title'][:55]}")
    if pos:
        lines.append(f"\n  Positive updates ({len(pos)} posts):")
        for d in pos: lines.append(f"    - {d['title'][:55]}")
    if not neg and not pos and docs:
        lines.append(f"  Most relevant: {docs[0]['title'][:55]}")
    lines.append(f"\n  Communities: {', '.join(subs)}")
    return "\n".join(lines)

# FRAMEWORK 1 - PURE PYTHON
class PureMultiAgent:
    def run(self, query):
        print(f"\n  FRAMEWORK 1 - Pure Python Multi-Agent")
        bar()
        print(f"  Manager: Think and Plan -> Rewriter -> Retriever -> Evaluator")
        print(f"  Rewriter: calling Llama 3.1 locally...")
        pause()
        result = call_llama(f'Rewrite for software update search: "{query}" - return only the rewritten query')
        if "[Ollama" in result:
            result = query + " software update bug fixes release"
        print(f"  Rewriter output: {result[:60]}")
        docs = search_docs(result)
        print(f"  Retriever: found {len(docs)} docs from {len(DOCS)} posts")
        for d in docs:
            icon = "RED" if d["sentiment"]=="Negative" else "GREEN" if d["sentiment"]=="Positive" else "NEUTRAL"
            print(f"    [{icon}] {d['title'][:50]}")
        terms = set(query.lower().split())
        quality = round(min(len(terms & set(docs[0]["title"].lower().split()))/max(len(terms),1),1.0),2) if docs else 0.0
        signal = "POSITIVE" if quality >= 0.15 else "NEGATIVE - retrying"
        print(f"  Evaluator: quality={quality} | RLAIF={signal}")
        if quality < 0.15:
            docs = search_docs(query + " software update release")
            quality2 = round(min(len(terms & set(docs[0]["title"].lower().split()))/max(len(terms),1),1.0),2) if docs else 0.0
            print(f"  Manager: retried -> quality={quality2}")
        return build_answer(docs, query)

# FRAMEWORK 2 - LANGCHAIN
def run_langchain(query):
    print(f"\n  FRAMEWORK 2 - LangChain ReAct Agent")
    bar()
    try:
        from langchain_ollama import ChatOllama
        from langchain.tools import tool
        from langchain.agents import create_react_agent, AgentExecutor
        from langchain_core.prompts import PromptTemplate
        from langchain.callbacks.base import BaseCallbackHandler

        @tool
        def search_updates(query: str) -> str:
            """Search Reddit posts about software updates and bugs. Args: query: search terms"""
            docs = search_docs(query)
            return json.dumps([{"title":d["title"],"subreddit":d["subreddit"],"sentiment":d["sentiment"]} for d in docs],indent=2)

        @tool
        def get_negative_posts() -> str:
            """Get the most negative Reddit posts about software updates."""
            neg = sorted([d for d in DOCS if d["sentiment"]=="Negative"],key=lambda x:x["divergence"],reverse=True)[:5]
            return json.dumps([{"title":d["title"],"subreddit":d["subreddit"],"divergence":round(d["divergence"],3)} for d in neg],indent=2)

        class Logger(BaseCallbackHandler):
            def on_agent_action(self,action,**k): print(f"  Tool: {action.tool} | Input: {str(action.tool_input)[:50]}")
            def on_agent_finish(self,finish,**k): print(f"  Chain complete")

        llm = ChatOllama(model="llama3.1",temperature=0)
        tools = [search_updates, get_negative_posts]
        prompt = PromptTemplate.from_template("""You are a software update research assistant.
Tools: {tools} | Tool names: {tool_names}
Question: {input}
Thought: {agent_scratchpad}
Use format: Thought/Action/Action Input/Observation/Final Answer""")
        agent = create_react_agent(llm=llm,tools=tools,prompt=prompt)
        executor = AgentExecutor(agent=agent,tools=tools,verbose=False,handle_parsing_errors=True,max_iterations=3,callbacks=[Logger()])
        result = executor.invoke({"input":query})
        return result.get("output","No answer")
    except ImportError:
        return "LangChain not installed - run: pip install langchain==0.2.16 langchain-core==0.2.38 langchain-ollama langchain-community==0.2.16"
    except Exception as e:
        return f"LangChain error: {e}"

# FRAMEWORK 3 - SMOLAGENTS
def run_smolagents(query):
    print(f"\n  FRAMEWORK 3 - smolagents ToolCallingAgent (HuggingFace)")
    bar()
    try:
        from smolagents import ToolCallingAgent, LiteLLMModel, tool

        @tool
        def search_software_updates(query: str) -> str:
            """Search Reddit posts about software updates bugs and releases. Args: query: what to search for"""
            docs = search_docs(query)
            return json.dumps([{"title":d["title"],"subreddit":d["subreddit"],"sentiment":d["sentiment"]} for d in docs],indent=2)

        @tool
        def get_negative_reactions(top_n: str = "5") -> str:
            """Get software releases with the most negative community reactions. Args: top_n: number of results"""
            try: n = min(int(str(top_n).strip()),10)
            except: n = 5
            neg = sorted([d for d in DOCS if d["sentiment"]=="Negative"],key=lambda x:x["divergence"],reverse=True)[:n]
            return json.dumps([{"title":d["title"],"subreddit":d["subreddit"],"divergence":round(d["divergence"],3)} for d in neg],indent=2)

        model = LiteLLMModel(model_id="ollama/llama3.1",api_base="http://localhost:11434")
        agent = ToolCallingAgent(tools=[search_software_updates,get_negative_reactions],model=model,max_steps=3,verbosity_level=1)
        return agent.run(query)
    except ImportError:
        return "smolagents not installed - run: pip install smolagents litellm"
    except Exception as e:
        return f"smolagents error: {e}"

# RUNNER
DEMO_Q    = "What bugs were fixed in the latest software update?"
COMPARE_Q = "Which software releases got the most negative community reaction?"

def run_all(query):
    print(); bar("=")
    print(f"  QUERY: {query}")
    print(f"  Running through all 3 frameworks...")
    bar("=")

    t0=time.time(); r1=PureMultiAgent().run(query); t1=round(time.time()-t0,1)
    t0=time.time(); r2=run_langchain(query);         t2=round(time.time()-t0,1)
    t0=time.time(); r3=run_smolagents(query);        t3=round(time.time()-t0,1)

    print(f"\n{'='*W}")
    print(f"  RESULTS COMPARISON")
    bar("=")
    print(f"\n  [1] Pure Python ({t1}s)"); bar("-"); print(r1)
    print(f"\n  [2] LangChain ({t2}s)");   bar("-"); print(str(r2)[:300])
    print(f"\n  [3] smolagents ({t3}s)");  bar("-"); print(str(r3)[:300])
    print(f"\n  Timing: Python={t1}s | LangChain={t2}s | smolagents={t3}s")
    bar("=")

def show_why():
    print(); bar("=")
    print("  WHY MULTI-AGENT?")
    bar("=")
    print("""
  SINGLE AGENT problem:
    One model does everything -> confused, shallow, no feedback

  MULTI-AGENT solution:
    Each agent has ONE job -> Manager coordinates -> RLAIF retries

  3 FRAMEWORKS - same idea, different tools:
    Pure Python -> full control, every line yours
    LangChain   -> industry standard (Google, Microsoft)
    smolagents  -> HuggingFace official, from the course
    """)

def main():
    print(); bar("=")
    print(f"  Unified Multi-Agent Demo | {len(DOCS)} Reddit posts | Llama 3.1")
    bar("-")
    print("  Commands: 'why' | 'compare' | 'demo' | 'exit' | any question")
    bar("=")
    while True:
        try: cmd = input("\n> ").strip().lower()
        except (KeyboardInterrupt,EOFError): print("\nGoodbye!"); break
        if not cmd: continue
        if cmd in ("exit","quit"): print("Goodbye!"); break
        elif cmd == "why": show_why()
        elif cmd == "compare": run_all(COMPARE_Q)
        elif cmd == "demo": run_all(DEMO_Q); run_all(COMPARE_Q)
        else: run_all(cmd)

if __name__ == "__main__": main()
