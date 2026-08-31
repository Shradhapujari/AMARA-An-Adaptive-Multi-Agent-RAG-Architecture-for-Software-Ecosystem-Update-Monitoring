# Multi-Agent RAG System Evaluation Report

- Dataset: `data/benchmark_100.json` (100 questions, hash `67177cd53aab`)
- Judge: `ollama:llama3.1` (active)
- Systems: marag, single_agent
- Seed: 42  |  top_k: 4

Values are mean ± 95% CI. IR metrics use LLM-judged graded relevance (qrels). Answer metrics are LLM-as-judge (0–1).

## Head-to-head

| System | mrr | ndcg@1 | recall@1 | ndcg@3 | recall@3 | ndcg@5 | recall@5 | faithfulness | answer_relevance | correctness | self_quality | latency_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| marag | 0.817±0.072 | 0.770±0.081 | 0.289±0.064 | 0.658±0.066 | 0.376±0.065 | 0.618±0.064 | 0.391±0.064 | 0.723±0.040 | 0.995±0.004 | 0.298±0.099 | 0.865 | 23.55 |
| single_agent | 0.808±0.073 | 0.760±0.083 | 0.284±0.065 | 0.649±0.069 | 0.360±0.064 | 0.618±0.065 | 0.401±0.066 | 0.861±0.035 | 0.991±0.009 | 0.545±0.162 | — | 28.41 |

## Per-category ndcg@1

| Category | marag | single_agent |
|---|---|---|
| bugs | 0.950±0.098 | 0.950±0.098 |
| community | 0.917±0.115 | 0.917±0.115 |
| general | 1.000±0.000 | 1.000±0.000 |
| releases | 0.617±0.213 | 0.567±0.218 |
| security | 0.367±0.211 | 0.367±0.211 |

> Note: `self_quality` is Multi-Agent RAG System's original built-in heuristic, shown only for reference — it is not a standard metric.
