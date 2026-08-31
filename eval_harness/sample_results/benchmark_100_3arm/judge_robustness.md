# Judge robustness — `run_1788146393_67177cd53aab`

Original judge: `ollama:llama3.1`  ·  second judge: `ollama:qwen2.5:7b-instruct`
Questions re-judged: 40  ·  arms: `marag_llm` vs `marag`

Answers are read from the run as produced; only the judge changes.

## 1. Agreement between the judges

| metric | mean (original) | mean (second) | mean abs diff | exact | within 0.1 |
|---|---|---|---|---|---|
| faithfulness | 0.809 | 0.796 | 0.129 | 29% | 48% |
| answer_relevance | 0.997 | 0.936 | 0.061 | 39% | 100% |

## 2. Does `marag_llm` − `marag` on faithfulness survive?

| judge | Δ | p | W/T/L |
|---|---|---|---|
| `ollama:llama3.1` | +0.111 | 0.0122 | 21/11/8 |
| `ollama:qwen2.5:7b-instruct` | +0.107 | 0.0000 | 24/13/3 |

**SURVIVES — same direction, significant under both judges**

