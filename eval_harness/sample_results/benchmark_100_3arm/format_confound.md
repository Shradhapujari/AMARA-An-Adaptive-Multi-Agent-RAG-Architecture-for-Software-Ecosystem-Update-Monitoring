# Format vs retrieval decomposition — `run_1788146393_67177cd53aab`

Arms present: marag, marag_llm, single_agent  ·  questions: 90

Arms folded in from: `run_1788160991_67177cd53aab`

**10 question(s) dropped** because `marag` and `marag_llm` retrieved different documents there, so a difference between them would not be a format effect: [168, 202, 228, 295, 44, 48, 53, 61, 77, 81]. This happens when the arms were measured in separate runs over a corpus that was not actually frozen.

## 1. The two multi-agent arms retrieve identically

`marag` vs `marag_llm` identical ranked doc_ids: **90/90**. Anything that differs between them is the answer rendering, nothing else.

## 2. Faithfulness: the gap is the format

| comparison | what it measures | result |
|---|---|---|
| `marag` − `single_agent` | retrieval + format | mean -0.144  W/T/L 14/23/53  (n=90) |
| `marag_llm` − `marag` | format alone | mean +0.119  W/T/L 51/22/17  (n=90) |
| `marag_llm` − `single_agent` | retrieval alone | mean -0.025  W/T/L 8/65/17  (n=90) |

The format term (+0.119) accounts for the whole mixed gap (-0.144); with format matched, the retrieval term is -0.025.

## 3. Answer length by arm

| arm | median chars | mean chars |
|---|---|---|
| `marag` | 2060 | 2037 |
| `marag_llm` | 286 | 310 |
| `single_agent` | 274 | 304 |

## 4. A retrieval tie is not retrieval agreement

`marag` and `single_agent` return the same ranked docs on only **27/90** questions; 182 documents are retrieved by exactly one of them. Of those, the relevant ones split **8** to `marag` and **13** to `single_agent` — near-symmetric, so they offset and the aggregate metrics tie while the arms are not retrieving the same thing.

