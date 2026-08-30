# An Adaptive Multi-Agent RAG Architecture for Software Ecosystem Update Monitoring

> Multi-agent RAG system that answers software update questions — *"are there known Siri issues after iOS 26.4?"* — by integrating release notes, security advisories, and community discussions, with a self-improving retrieval memory that learns from its own outcomes. Runs locally on Llama 3.1 8B.

📄 **Paper:** *An Adaptive Multi-Agent RAG Architecture for Software Ecosystem Update Monitoring* — presented at **AgenticSE '26** (Workshop on Agentic Software Engineering, ACM CAIS 2026), San Jose, CA, May 26–29, 2026. [[PDF](https://drive.google.com/file/d/1WssnrTSiUxtYd2wWdV5QUKbIcB2-iPLH/view?usp=sharing)]

👩‍💻 **Authors:** Shradha Devendra Pujari, Dr. Solomon Berhe — University of the Pacific, Department of Computer Science.

---

## TL;DR

- **+17.2%** retrieval quality over a single-agent RAG baseline (paired *t*-test, *t*(49) = 2.32, *p* = 0.020).
- **+9.3%** additional improvement from self-improvement memory across successive queries — no human feedback, no retraining (Cohen's *d* = 0.83).
- **Zero hallucinated version numbers** across version-specific evaluation; every claim traces back to a retrieved source.
- Runs **fully locally** on Apple Silicon (24 GB unified memory) via Ollama. No closed-model API calls.

---

## Why this exists

Every time a software update ships — iOS, Linux, Firefox, a NAS firmware, whatever — the information you need is scattered. Release notes tell you the official version. CVE feeds tell you the security side. Reddit tells you what's actually breaking for real users. Ask a normal single-agent RAG system *"are there Siri issues after iOS 26.4?"* and you get a vague answer with no real evidence.

This system is built around the observation that single-agent RAG systems do query rewriting, retrieval, and evaluation all in one reasoning pass — which causes vocabulary mismatch (users say *"iPhone,"* release notes say *"iOS"*) and offers no feedback loop when retrieval fails. We decompose those tasks into four specialized agents and add a persistent memory of what worked.

---

## Architecture

Four specialized agents coordinated by an Orchestrator, connected through a retrieval-level feedback loop:

```
                  ┌──────────────────────┐
                  │   User Question      │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │  Orchestrator Agent  │
                  └──────────┬───────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌────────────────┐   ┌─────────────────┐
│ Query Rewriter│──▶│ Retriever      │──▶│ Evaluator       │
│   (Llama 3.1) │   │ (vendor-aware) │   │ (score 0.0–1.0) │
└───────────────┘   └────────────────┘   └─────────┬───────┘
        ▲                                          │
        │      retry if score < θ = 0.30           │
        └──────────────────────────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Generated Answer    │
                  │  (grounded + cited)  │
                  └──────────────────────┘
```

| Agent | Responsibility |
|---|---|
| **Orchestrator** | Coordinates the pipeline; manages retrieval retries when the Evaluator flags low quality. |
| **Query Rewriter** | Normalizes user terminology to match how vendors actually write release notes. Pulls from Self-Improvement Memory to bias future queries toward learned-successful terms. |
| **Retriever** | Vendor-aware search across a registry of **14,223 vendors** and **628 software-related subreddits**. Restricts retrieval to vendor-specific sources when a vendor is detected. |
| **Evaluator** | Deterministic 0.0–1.0 score combining retrieval volume, release-note matches, community matches, and CVE matches. Triggers a retry if score < 0.30. |

### Self-Improvement Memory

Every query-expansion term that leads to a successful retrieval accumulates a positive score. Failed retrievals decrement scores. The Query Rewriter uses these scores to bias future queries. **No human feedback, no labeled data, no model retraining.**

Top learned terms after 50 queries (interpretable on inspection): `vulnerability` (+2.20), `patch` (+1.58), `advisory` (+1.23), `update` (+1.15), `kernel` (+0.98). These are exactly the terms a domain expert would tell you matter — the system found them on its own from retrieval outcomes.

---

## Data sources

**Verified (Tier 1):**
- Vendor registry — 6,578 entries
- Software release notes — 31,958 entries
- CVE / vulnerability advisories — 24,139 entries
- LLM / AI model releases — served from the same `/api/v/` collection, filtered by product type/name (OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, Qwen, xAI, Ollama). Browsable at <https://releasetrain.io/?type=llm>
- Apple Developer RSS, CISA KEV, CIRCL CVE Atom feed (dedicated Apple-side coverage)

**Community (Tier 2):**
- Reddit discussions — 208,466 posts
- Software update risk discussions — 2,637 posts
- Vendor-specific subreddit queries
- Google News

Verified and community sources are kept separate and weighted differently in the Evaluator's score.

The lake behind these endpoints is a MongoDB store covering Reddit posts, Stack
Overflow posts, software release notes, CVE advisories, and LLM/AI model
releases. The retrieval layer currently consumes release notes, CVE, LLM
releases, and Reddit; **Stack Overflow is present in the lake but not yet wired
into the Retriever** — see `TODO` in the roadmap below.


## Evaluation

Two independent layers, so a result never rests on our own scoring alone.

**1. IR + judge metrics** (`eval_harness/`) — recall@k, nDCG@k, precision@k, MRR
against pooled, judge-labelled qrels, plus LLM-judged answer scores.

```bash
python -m eval_harness.run_eval --dataset table_50_questions.json --limit 50
```

**2. Established-benchmark scoring** (`eval_harness/benchmarks.py`) — deterministic
CRAG-style labelling of every answer as `correct` / `incorrect` / `missing`, with

```
accuracy = correct/n     hallucination = incorrect/n
missing  = missing/n     crag_score    = accuracy - hallucination
```

No LLM in the loop, so it is reproducible and independent of the model under
test. `crag_score` penalizes a confident wrong answer and merely declines to
reward an abstention — which is exactly the property our own Evaluator score
cannot express, and the reason a system that says *"the sources do not answer
this"* is scored strictly above one that guesses.

```bash
python -m eval_harness.run_eval --dataset crag_questions.jsonl --benchmark crag
```

Answer matching is version-aware: a prediction naming the right product but the
wrong version scores `incorrect`, not `correct`.

**3. Head-to-head comparison** (`eval_harness/compare.py`) — paired statistics
over a completed run, since every system answers the same questions:

```bash
python -m eval_harness.compare results/<run_id> --baseline single_agent \
    --metrics ndcg@5,recall@5,mrr,answer_score
```

Reports the mean paired difference with a bootstrap 95% CI, a paired t-test, a
non-parametric bootstrap p-value, Holm correction across the comparison family,
and win/tie/loss counts. Pure Python — no scipy or numpy needed. The t-test
agrees with `scipy.stats.ttest_rel` to 1e-8 (see `tests/test_compare.py`).

Treat a difference as real only when the CI excludes zero, the Holm-corrected
p-value holds, **and** the win/loss split points the same way. A large mean
difference with a near-even win/loss split means outliers are carrying it.

### Tests

```bash
python -m pytest tests/ -q      # 54 offline tests, no network required
```


---

## Results

### Retrieval quality by category (50 questions)

| Category | Single-Agent | 4-Agent | Improvement |
|---|---:|---:|---:|
| Security | 0.630 | 0.750 | **+19.0%** |
| Bugs | 0.756 | 0.833 | +10.3% |
| Releases | 0.667 | 0.723 | +8.5% |
| Community | 0.730 | 0.850 | +16.4% |
| General | 0.600 | 0.750 | **+25.0%** |
| **Overall** | **0.680** | **0.798** | **+17.2%** |

*Paired t-test: t(49) = 2.32, p = 0.020.*

### Self-improvement over the evaluation run

| Tertile | Mean retrieval quality |
|---|---:|
| Q1–Q17 (early) | 0.756 |
| Q34–Q50 (late) | 0.826 |

*+9.3% improvement, t(16) = 2.18, p = 0.043, Cohen's d = 0.83.*

### Answer accuracy

On version-specific questions, the system correctly identified Linux v7.0.0 (April 13, 2026) and Firefox v149.0.1 (April 7, 2026) from the corresponding release sources. On a supplementary 10-question live evaluation: **4 fully correct, 6 partially correct, 0 unsupported version numbers or CVE identifiers generated.**

Raw per-question results are in `eval_50_results_v2.json` and the per-question results table. Ablation results are in `ablation_results.json`.

---

## Tech stack

- **Models:** Llama 3.1 8B (primary), Mistral 7B (tested) — local via [Ollama](https://ollama.com), temperature 0
- **Frameworks:** LangChain, smolagents
- **Embeddings & search:** HuggingFace BGE-Large, FAISS, ChromaDB
- **Frontend:** Streamlit
- **Adaptation:** RLAIF-style retrieval-level feedback, persistent term-weight memory
- **Hardware tested:** Apple Silicon, 24 GB unified memory, Metal GPU acceleration

Multiple implementation variants are provided (Pure Python in `multiagent_rag_v3.py`, smolagents in `rag_smolagents_v2.py`) — they produce equivalent retrieval results on the evaluation dataset. The Pure Python implementation gives the cleanest execution trace.

---

## Getting started

### Requirements

- Python 3.11
- [Ollama](https://ollama.com/download) with `llama3.1:8b` pulled
- ~16 GB RAM minimum (24 GB recommended for comfortable inference)
- macOS/Linux (Apple Silicon recommended for Metal acceleration)

### Setup

```bash
# Clone
git clone https://github.com/Shradhapujari/Adaptive-Multi-Agent-RAG-Architecture-for-Software-Ecosystem-Update-Monitoring.git
cd Adaptive-Multi-Agent-RAG-Architecture-for-Software-Ecosystem-Update-Monitoring

# Virtual environment
python3.11 -m venv venv311
source venv311/bin/activate

# Dependencies
pip install -r requirements.txt

# Pull the model
ollama pull llama3.1:8b
```

### Run the Streamlit demo (recommended)

The easiest way to try this system is the Streamlit interface — ask a question and watch the four agents coordinate live:

```bash
streamlit run marag_app.py
```

Then open the URL Streamlit prints (usually `http://localhost:8501`).

### Run from the CLI

For scripted use or to inspect execution traces directly:

```bash
python multiagent_rag_v3.py
```

### Reproduce the evaluation

```bash
python evaluate_v3.py
```

> ⚠️ The system relies on live software ecosystem APIs. Results may shift over time as upstream data changes. For controlled comparison, snapshot the API responses (see *Reproducibility Notes* in the paper, §5.3).

---

## Repository layout

Key entry points:

| File | What it is |
|---|---|
| `marag_app.py` | Streamlit demo — primary way to interact with the system |
| `multiagent_rag_v3.py` | Main four-agent system (pure Python implementation) |
| `unified_agent_system.py` | Single-agent baseline used for comparison |
| `rag_smolagents_v2.py` | Equivalent implementation using HuggingFace smolagents |
| `self_improving_agent.py` | Persistent term-weight memory for the Self-Improvement Memory |
| `evaluate_v3.py` | Evaluation harness (latest version) |
| `test_apis.py` | Standalone test of the underlying data-source APIs |
| `run_all.sh` | Shell script to run the full evaluation pipeline |

Data and results:

| Path | What's in it |
|---|---|
| `data/` | Evaluation question sets and supporting data |
| `eval_50_results_v2.json` | Per-question scores for the 50-question evaluation |
| `ablation_results.json` | Ablation study results (per-component contribution) |
| `accuracy_test_results.json`, `accuracy_postfix_results.json` | Answer-accuracy evaluations |
| `MultiAgent_Presentation_20thMarch.pptx` | Earlier presentation slides |

Older / archived versions of the main scripts (`multiagent_rag.py`, `multiagent_rag_v2.py`, `evaluate.py`, `evaluate_v2.py`, `app.py`, etc.) are kept in the repo root for reference and reproducibility.

---

## Known limitations

We're explicit about these in the paper (§5) — they're real, and good directions to push on:

- **Apple is structurally harder.** Apple doesn't publish to the same release database other vendors do. We added dedicated Apple sources (Developer RSS, CISA KEV, CIRCL CVE) and iOS/Apple synonym expansion, but full coverage requires broader vendor onboarding.
- **Temporal queries.** *"What was the Linux version on January 1st 2026?"* — the date constraint isn't currently passed to retrieval, so we return the latest version. Fixable.
- **Vendor extraction failures** on phrases like *"Synology NAS unreachable after upgrade"* — preprocessing strips domain terms. Future fix: embedding-based vendor matching over the full registry.
- **Community-source reliability.** Reddit is the weakest link. We require ≥10 comments, ≥3 author replies, quality ≥ 0.3, and separate verified from community sources — but a single popular wrong post can still bias an answer.
- **Evaluation size.** 50 questions is statistically significant but small. A larger multi-ecosystem benchmark is the next study.
- **Heuristic thresholds** (θ = 0.30 for retry, the Evaluator scoring weights) were manually tuned. Learned reward models and adaptive threshold selection are in the roadmap.

---

## Roadmap

- [ ] Larger multi-ecosystem benchmark
- [ ] Embedding-based vendor matching (replace static alias dictionary)
- [ ] Learned reward model for the Evaluator (replace heuristic scoring)
- [ ] Adaptive threshold selection
- [ ] Head-to-head comparison with Self-RAG, CRAG, MA-RAG, MAIN-RAG (requires porting them to the software-ecosystem retrieval setting)
- [ ] Cross-post agreement analysis for community-source credibility
- [ ] Multilingual evaluation
- [ ] Persistent cross-session memory with decay/capping to prevent drift at scale

---

## Citation

If you build on this work, please cite:

```bibtex
@inproceedings{pujari2026adaptive,
  title     = {An Adaptive Multi-Agent RAG Architecture for Software Ecosystem Update Monitoring},
  author    = {Pujari, Shradha Devendra and Berhe, Solomon},
  booktitle = {Proceedings of the Workshop on Agentic Software Engineering (AgenticSE '26)},
  year      = {2026},
  address   = {San Jose, CA, USA},
  publisher = {ACM}
}
```

---

## Collaborate

I'm actively looking for collaborators on:

- Larger-scale evaluation across multiple software ecosystems
- Learned reward models / adaptive thresholds to replace the current heuristics
- Community-source credibility estimation
- Multilingual extensions
- Head-to-head benchmarks against other multi-agent RAG systems

If anything here connects to what you're working on — or you'd like to contribute — open an issue or reach out directly.

**Contact:** Shradha Devendra Pujari — `s_pujari@u.pacific.edu` · [GitHub @Shradhapujari](https://github.com/Shradhapujari) · [LinkedIn](https://linkedin.com/in/shradha-pujari-98900)

**Advisor:** Dr. Solomon Berhe — `sberhe@pacific.edu`

---

## Acknowledgments

Thanks to the maintainers of public software ecosystem data sources, online communities, and open APIs for making software-related information accessible for research. Their continued contributions enable the collection and evaluation of real-world software update questions that made this study possible.

---

## License

MIT — see [`LICENSE`](LICENSE) for details. You're free to use, modify, and build on this work; attribution is appreciated.
