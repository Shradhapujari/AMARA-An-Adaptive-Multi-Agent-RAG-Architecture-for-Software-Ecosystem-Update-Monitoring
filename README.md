# AMARA — Adaptive Multi-Agent RAG Architecture

> **Adaptive Multi-Agent RAG Architecture for Software Ecosystem Monitoring**  
> University of the Pacific · Agentic AI Research · 2026

**Shradha Devendra Pujari** · Dr. Solomon Berhe

---

## What is AMARA?

AMARA is a self-improving multi-agent system that monitors software ecosystems in real time by coordinating 4 specialized AI agents over live APIs to answer questions like:

- *"Any critical Linux updates published today?"*
- *"What bugs were fixed in the latest Python release?"*
- *"Are there any CVE vulnerabilities in Django?"*
- *"How did the community react to the latest MacOS update?"*

---

## Architecture
```
User Query
    ↓
Manager Agent (Orchestrator) — Think & Plan
    ↓           ↓            ↓           ↓
Query       Community    Release      CVE
Rewriter    Agent        Notes        Agent
(Llama 3.1) (Reddit API) (Releases)   (CVE API)
    ↓           ↓            ↓           ↓
         RLAIF Evaluator (quality 0–1)
                 ↓
         Self-Improvement Memory
                 ↓
         Grounded Final Answer
```

---

## Live APIs

| Agent | Endpoint | Purpose |
|-------|----------|---------|
| Community | `releasetrain.io/api/reddit/query/positive` | Live Reddit posts |
| Release Notes | `releasetrain.io/api/v/` | Live software releases |
| CVE Security | `releasetrain.io/api/reddit/query/cve` | Security vulnerabilities |
| Query Rewriter | Llama 3.1 via Ollama (local) | Semantic gap bridging |

---

## Self-Improvement Model

| Level | Mechanism | Description |
|-------|-----------|-------------|
| Level 1 | RLAIF Retry | Bad result → retry automatically |
| Level 2 | Strategy Memory | Learns which terms work — Zero Human Feedback |
| Level 3 | MiniMax M2.7 | LLM weight adaptation from web data |

---

## Files

| File | Description |
|------|-------------|
| `amara_app.py` | Streamlit web app — main prototype |
| `multiagent_rag_v3.py` | Core multi-agent system with Llama 3.1 |
| `multiagent_rag_v2.py` | Backup — no LLM dependency |
| `self_improving_agent.py` | Self-improvement with MiniMax M2.7 |
| `unified_demo.py` | All 3 frameworks side by side |
| `evaluate.py` | Evaluation framework — baseline vs AMARA |
| `DemoMain.py` | LangChain single agent (baseline) |
| `rag_smolagents_v2.py` | HuggingFace smolagents implementation |

---

## Quick Start
```bash
# Clone the repo
git clone https://github.com/Shradhapujari/AMARA-MultiAgent.git
cd AMARA-MultiAgent

# Install dependencies
pip install streamlit requests smolagents litellm langchain==0.2.16 langchain-core==0.2.38 langchain-ollama langchain-community==0.2.16

# Pull the LLM (runs locally — no API key needed)
ollama pull llama3.1

# Run the web app
streamlit run amara_app.py

# Or run the terminal demo
python multiagent_rag_v3.py
```

---

## Demo Commands
```bash
python multiagent_rag_v3.py     # type 'why' then 'demo'
python unified_demo.py          # type 'compare'
python self_improving_agent.py  # type 'demo' then 'memory'
python evaluate.py --quick      # run evaluation
streamlit run amara_app.py      # web UI
```

---

## Conference Paper

*"AMARA: An Adaptive Multi-Agent RAG Architecture for Software Ecosystem Monitoring"*  
**MobiSPC 2026** · Elsevier · Athens, Greece · August 18–20, 2026

---

## Related Work

Mohammed Fahad — RAG-Based Semantic Retrieval (single agent baseline)
- Slides: https://se4cps.github.io/lab/research/2026okip/
- Demo: https://releasenotesrec-agentgit-ryuf7vkcm5wukd8wa4busk.streamlit.app/

**AMARA extends this with multi-agent orchestration, RLAIF feedback, and self-improvement.**

---

## License

MIT License — free to use, modify, and distribute.
