# Speaker script — Week 2 implementation review, 3 September 2026

Companion to [`2026-09-03-week2-implementation-review.pptx`](2026-09-03-week2-implementation-review.pptx).

Each slide has three parts: **Say this** (the talk track), **Terms** (short
definitions for anything jargon-shaped on the slide), and **If asked** (the
questions the slide invites, with answers). Every number here is in the repo —
`eval_harness/FINDINGS.md` for the argument, `results/PROVENANCE.md` for the run
id behind each figure.

Two habits that make the whole meeting go better:

- **When a number is uncertain, say so before you are asked.** The caveat
  register on slide 14 exists so that "I don't know yet" is a normal sentence in
  this project rather than an admission.
- **Never quote a figure you cannot trace.** If Dr. Berhe asks where a number
  comes from and the answer is not a run id, the right answer is "let me check
  that before I claim it."

---

## Slide 1 — Title

**Say this**

> This is a full review rather than a week's status. I want to cover what the
> system is, what we measure it with, everything we have found so far, and how
> we found it. The short version is that the project has turned into a negative
> result plus its remedy, and the negative result is better evidenced than the
> original positive claim ever was.

**If asked**

*"Why are you reviewing the whole project in week 2?"*
Because the finding that changed the direction of the work landed between the
conference paper and now, and the argument only makes sense end to end. From
next week the reviews go back to a week at a time.

---

## Slide 2 — The arc of the work in one slide

**Say this**

> Five steps. The published claim of a 17.2% retrieval gain did not survive
> re-measurement under standard metrics. The cause turned out to be a real
> defect, and it was at fetch time, not ranking time. We fixed it two ways.
> The repaired system reaches parity with a single-agent baseline, not
> superiority — confirmed now at three sample sizes. And what *does* help is
> grounding the question, which we can now measure separately from the
> multi-agent coordination.

**Terms**

| Term | Meaning |
|---|---|
| **Retrieval** | Fetching candidate documents for a question, before any answer is written. |
| **Baseline (single-agent)** | One model doing rewriting, retrieval and answering in one pass — what the multi-agent system has to beat. |
| **Parity** | The two systems are statistically indistinguishable, not that one narrowly won. |
| **Grounding** | Resolving what the question actually refers to — which vendor, which product, which date window — before searching. |
| **Coordination** | The multi-agent decomposition itself: separate rewriter, retriever, evaluator, manager. |

**If asked**

*"So the whole project failed?"*
No. The system works and is deployed. What failed is one specific claim — that
splitting the work across agents is what improved retrieval. The defect we found
in the process is a concrete, transferable failure mode, and the grounding
result is a positive finding with a p-value behind it.

*"Why is a negative result publishable?"*
Because prior work motivates query rewriting for recall, and nobody has
published the failure mode where rewriting *replaces* the user's query and
silently destroys recall at fetch time. It is measured, mechanistically
explained, and the fix is three lines of behaviour change. That is more useful
to a practitioner than another small improvement claim.

---

## Slide 3 — The system: four evaluated agents, two added after

**Say this**

> Four agents were in the evaluation: the Query Rewriter, the Retriever, the
> Evaluator, and the Manager that coordinates them. Two more — the Temporal
> Grounder and the Answer Presenter — were added to the demo after the
> evaluation was finished, so they are marked as such everywhere and no reported
> number depends on them. Behind the rewriter there is a self-improvement memory
> that scores expansion terms by whether they led to a successful retrieval.

**Terms**

| Term | Meaning |
|---|---|
| **Query rewriting** | Rephrasing the user's question into the vocabulary documents actually use — a user says "iPhone", release notes say "iOS". |
| **Union fetch** | Sending *both* the original and the rewritten phrasing to every endpoint and merging the results, instead of sending only the rewrite. |
| **Reranking** | Re-ordering the fetched candidates before they reach the answer step. |
| **RLAIF** | Reinforcement Learning from AI Feedback — the system scores its own retrieval and uses that signal instead of human labels. |
| **Self-improvement memory** | A running score per expansion term: terms that preceded good retrievals go up, terms that preceded bad ones go down. No retraining, no human feedback. |

**If asked**

*"Why is the rewriter the place the defect lived?"*
Not because rewriting is wrong — the rewrite does find documents the baseline
misses. The defect was in how its output was *used*: it substituted for the
user's wording rather than adding to it.

*"The Evaluator threshold — 0.15 or 0.30?"*
0.15 is the retry threshold. 0.30 is a different constant in the same method, a
quality floor for tier-1 and Apple sources. An earlier write-up conflated them;
the docs now say which is which. This matters because it explains why the retry
rung never fired in the ablation — see slide 10.

*"Why add the two extra agents after evaluating?"*
They fix demo-facing problems — "today" needing to become a date, and bullet
templates reading badly. Adding them to the evaluated set would have meant
re-running everything, and they would have confounded the comparison. Keeping
them outside the measured system and labelling them is the honest option.

---

## Slide 4 — The corpus and the four question sets

**Say this**

> The retrieval side runs over live endpoints on a MongoDB lake — roughly 32,000
> release notes, 24,000 CVE advisories, 208,000 Reddit posts, plus Apple's RSS,
> CISA KEV and CIRCL. Verified sources and community sources are kept separate
> and weighted differently, because Reddit is the weakest link. On the
> evaluation side there are four question sets, and it matters which one a number
> came from: the original 50 gave the +17.2%, 10 hand-judged questions are
> directional only, 100 carries the ablation ladder, and 300 is the headline.

**Terms**

| Term | Meaning |
|---|---|
| **CVE** | Common Vulnerabilities and Exposures — the standard public identifier for a security flaw. |
| **CISA KEV** | The US agency's "Known Exploited Vulnerabilities" catalogue — flaws confirmed to be exploited in the wild. |
| **Tier 1 / Tier 2** | Verified sources (vendor release notes, advisories) versus community discussion. Weighted differently in the Evaluator's score. |
| **Ecosystem** | One software family — iOS, a Linux distribution, a browser, a package manager. The 300-question set spans 24. |

**If asked**

*"Why not just use an existing IR benchmark?"*
None of them contain software-update questions over live release notes, CVE
feeds and community discussion at once. That combination is the problem we are
studying; a generic benchmark would not exercise it.

*"How do you know the mined questions are fair?"*
Two upstream data defects are handled rather than inherited. CVE rows label the
index token, not the affected product, so naive templating fabricates questions
like "Is iOS v4.2.0 vulnerable?" — rows we cannot attribute confidently are
dropped. Some feed dates are corrupt and are dropped for the same reason. Every
question carries a `source` field, so mined and templated items stay
distinguishable in analysis.

*"14,223 vendors on the last slide, 6,578 here — which is it?"*
Different things. 14,223 is the local product-name alias table the extractor
matches against. 6,578 is what the vendor-registry endpoint returns. The paper
distinguishes them; I should not merge them.

---

## Slide 5 — The evaluation harness

**Say this**

> This is the part I would argue is the real contribution alongside the pipeline.
> It measures standard IR metrics against judged relevance, plus three
> answer-quality scores from an LLM judge. It stays honest in four ways: it can
> freeze the corpus and replay it, so every arm sees byte-identical documents; it
> refuses to call a run comparable if any document host was read live during a
> replay; it checks that all arms saw the same candidates before reranking; and
> the relevance cache is written atomically and keyed by question text.

**Terms**

| Term | Meaning |
|---|---|
| **Recall@k** | Of all the documents known to be relevant, what fraction appear in the top *k*. |
| **Precision@k** | Of the top *k* documents, what fraction are relevant. |
| **nDCG@k** | Normalized Discounted Cumulative Gain. Sums the relevance of the top *k*, discounting each by its rank position, divided by the best possible ordering. 1.0 is a perfect ranking; it rewards putting relevant documents *high*, not merely including them. |
| **MRR** | Mean Reciprocal Rank — 1 divided by the rank of the first relevant document, averaged over questions. Rewards getting one right answer to the top. |
| **Qrels** | Query relevance judgments: the labels saying which document counts as relevant to which question. |
| **Pool recall** | What fraction of relevant documents are anywhere in the candidate pool before reranking. It is the *ceiling* — no reranker can promote a document that was never fetched. |
| **Faithfulness** | Is every claim in the answer supported by the retrieved context. Measures hallucination. |
| **Answer relevance** | Does the answer address the question that was asked. |
| **Record / replay** | Record: run live and save every HTTP response. Replay: serve the saved responses, so a later run sees exactly the same documents. |
| **Admissibility** | Our gate: a replay run that had to go live for any document is not comparable to other arms, and is rejected regardless of how good its numbers look. |

**If asked**

*"Why an LLM judge rather than human labels?"*
Cost and scale — 300 questions across three arms is 900 answers plus relevance
labels for thousands of documents. The judge is declared as an open threat, not
hidden: it currently shares a model family with the system under test, which is
exactly what Phase 4 is meant to fix.

*"Isn't pooled relevance biased?"*
Yes, and we say so. Only documents some arm actually retrieved get judged, so
absolute recall and nDCG are inflated. The *paired* within-run comparison stays
valid, because both arms share one pool. We report the paired comparison and
treat the absolute values as pool-relative.

*"Why does the PYTHONHASHSEED thing matter?"*
It is the subtlest bug we have found. Vendor extraction broke ties by iterating
a raw Python set, whose order is randomized per process. Each arm runs as a
separate process, so the identical question could resolve to a different vendor
on different arms and query different endpoints. A frozen corpus does not help
if the retrieval layer asks it different questions. Fixed with `sorted()` and
four regression tests.

---

## Slide 6 — Models, and where each one is used

**Say this**

> Everything reported so far runs locally on Ollama — no API key, no closed
> model. Llama 3.1 does rewriting, synthesis and judging; Mistral is the
> synthesis model held constant across arms in the frozen ladder;
> nomic-embed-text is the embedding reranker; qwen2.5 judged the ladder run
> specifically so the judge had written none of the answers it was scoring. The
> one model I need and cannot run is an independent judge — that is Phase 4 and
> it has been blocked on an OpenAI key since 31 August.

**Terms**

| Term | Meaning |
|---|---|
| **Ollama** | A local model runtime — models run on this machine, nothing leaves it. |
| **Embedding model** | Turns text into a vector; similarity is then cosine distance between vectors. Used here to rank candidates against the original question. |
| **BM25** | A classical lexical ranking function — term frequency, inverse document frequency, length normalization. Our middle reranker arm, between "none" and the embedding model. |
| **Judge independence** | The judge should not share a model family with the system it scores, or it may prefer its own phrasing and reward the wrong thing. |
| **Backend spec** | Our `"backend:model"` string — `ollama:llama3.1`, `openai:gpt-4o`. Switching backends is a spec string, not a code change. |

**If asked**

*"Why Llama 3.1 8B rather than a frontier model?"*
Three reasons: it runs on the 24 GB machine we have, it costs nothing per run
across thousands of calls, and a local model makes the whole evaluation
reproducible by anyone without a key. The cost is the judge-overlap threat,
which is why Phase 4 exists.

*"How much would the independent judge change?"*
Unknown, and that is the point — I cannot bound it without running it. What I
can say is which direction the bias would run: a judge sharing a family with one
arm would, if anything, flatter that arm, and the arm in question is ours. So
the parity result is unlikely to be hiding a win.

*"Gemini and GPT are Week 11 — why not sooner?"*
The provider layer already supports them; the work is a client class and a spec
string. But adding backends before the judge is independent would just multiply
an uncontrolled comparison. Judge first, then backends.

---

## Slide 7 — How the negative result was found

**Say this**

> Six findings in the order they actually happened, including the diagnosis that
> turned out to be wrong. F1 is the inversion — under standard metrics the
> multi-agent system scored 0.193 against the baseline's 0.743. F2 isolated the
> rewriter and found it helped zero of ten queries and hurt seven; we read that
> as a ranking problem. F3 is where that reading broke: three successively
> stronger rerankers lifted MRR from 0.250 to 0.625 while nDCG@3 stayed flat
> near 0.19. That is the moment the real cause became findable — if better
> ranking cannot close the gap, the missing documents are not being mis-ranked.
> They are not there. F4 confirmed it: 22 of 23 relevant documents the baseline
> retrieved were never fetched by us at all.

**Terms**

| Term | Meaning |
|---|---|
| **Inversion** | The result came out the opposite way round from the published claim. |
| **Ablation** | Turning one component off or swapping it, holding everything else fixed, to see what that component contributes. |
| **Fetch time vs ranking time** | Fetch time is which documents enter the candidate pool. Ranking time is how they are ordered once there. A document missing at fetch time can never be recovered by ranking. |

**If asked**

*"Why keep the wrong diagnosis in the write-up?"*
Because the sequence is the evidence. Anyone can assert a cause; showing that we
tested a plausible alternative, watched it fail in a specific way, and used that
failure to locate the real cause is what makes the final claim credible rather
than a guess that happened to work.

*"How did the original evaluation miss this?"*
The original metric was keyword overlap between the answer and a reference. A
system can score well on that while retrieving the wrong documents, if its
answer happens to use the right words. Standard IR metrics score the retrieved
documents directly, which is why they caught it.

---

## Slide 8 — The fix, and how much each half mattered

**Say this**

> Four configurations. The first three change only the reranker and barely move
> the number: 0.145, 0.212, 0.188. The fourth adds union fetch and it goes to
> 0.765. That is the whole story in one chart — the intuitive fix, better
> ranking, is the one that does not work, and the cheap fix, searching both
> phrasings, is the one that does. Worth adding: once both phrasings are
> retrieved, even the original substring boost reaches 0.597. Ranking against
> the original question adds 0.024 on top, which is not established at this
> sample size.

**Terms**

| Term | Meaning |
|---|---|
| **Substring boost** | The published ranking rule: score candidates by how much they match the first four tokens of the *rewritten* query — which, after a rewrite, are usually filler words. |
| **Dedupe by URL** | When both phrasings return the same document, it is counted once. |
| **Not established** | The difference is smaller than what this sample size can reliably detect — we do not claim it either way. |

**If asked**

*"Why does the baseline not benefit from union fetch?"*
Because `single_agent` passes the same string as both original and rewritten, so
the union collapses to one search. That is what makes this a clean before/after
for the multi-agent arm alone — the baseline is untouched.

*"Doesn't union fetch just double the cost?"*
It adds roughly one extra set of retrieval calls, which is most of why we are at
about 2× the baseline latency. It is a real cost and we report it rather than
burying it.

*"If reranking barely helps, why keep it?"*
Two reasons. `none` is kept deliberately as the ablation arm that reproduces the
published behaviour, so the comparison stays available. And the top-k sweep on
slide 11 shows the reranker matters more at larger *k* than the paper's `k=4`
config could reveal.

---

## Slide 9 — The headline run: n = 300, three arms

**Say this**

> The whole 300-question benchmark, three arms, synthesis model held constant,
> paired Wilcoxon with Holm correction. Every retrieval metric is null — the
> best p-value is 0.30. Read the tie column: 250 to 290 of 300 questions score
> identically. The one row that moves is faithfulness, and it is not a retrieval
> row. The obvious objection to a wall of ties is that both arms fetch the same
> documents so the test cannot see a difference. That does not hold: only a third
> of questions produce identical top-k lists, and our mean candidate pool is 23.1
> against the baseline's 15.5. We fetch half again as many documents, and
> different ones, and nothing moves. That is a stronger statement than parity —
> the extra retrieval is real and it is inert.

**Terms**

| Term | Meaning |
|---|---|
| **Paired test** | Each question is compared to itself across the two systems, so question difficulty cancels out. Much more sensitive than comparing two averages. |
| **Wilcoxon signed-rank** | A paired test that uses the ranks of the differences rather than their raw sizes. Distribution-free — it does not assume the differences are normally distributed. |
| **Holm correction** | We test several metrics at once, so some will look significant by chance. Holm adjusts the p-values to control the chance of *any* false positive across the family. Strictly more powerful than Bonferroni at the same guarantee. |
| **Null result** | We could not detect a difference. Not the same as proving there is none — but with 300 paired questions and ties this dominant, the room for a hidden effect is small. |
| **W / T / L** | On how many questions our system scored better, identically, or worse. |
| **p = 0.302** | If there were truly no difference, we would see a gap this large or larger about 30% of the time. Far from evidence of a difference. |

**If asked**

*"Why Wilcoxon rather than a paired t-test?"*
The per-question differences are not normally distributed and are dominated by
exact zeros. The signed-rank test does not assume normality, and it is the
standard choice for paired IR comparisons.

*"Null results are hard to interpret — how do I know your test could detect
anything?"*
That is exactly what the second box answers. If both arms retrieved the same
documents, ties would be uninformative. They do not: 65% of questions retrieve
materially different documents. The benchmark discriminates; the metric does not
move.

*"Then why do different documents give identical scores?"*
Because the documents that differ are mostly either both non-relevant or equally
relevant. Fetching more of the same kind of thing does not change nDCG.

*"Why hold the synthesis model constant?"*
Otherwise the comparison confounds retrieval with which model wrote the prose. A
bare baseline synthesises with Mistral while ours used Llama 3.1. Holding it
constant is a flag on the run, and it turns an answer-quality comparison from
meaningless into meaningful.

---

## Slide 10 — Separating grounding from coordination

**Say this**

> This is the run I would cite for anything that has to be exact. One hundred
> questions, eight arms, every arm served byte-identical documents from a frozen
> snapshot. It separates two things the architecture had been conflating.
> Grounding the question — resolving vendor, product and date before searching —
> is significant: +0.049 nDCG@3 at p = 0.007, and +0.051 recall@3 at p = 0.0035.
> Coordination on its own is null: p = 0.87. And a grounded single agent is
> statistically indistinguishable from the full pipeline. So the useful part of
> the architecture is the understanding, not the committee.

**Terms**

| Term | Meaning |
|---|---|
| **Ablation ladder** | A sequence of arms, each adding one capability to the previous, so you can attribute an improvement to a specific rung. |
| **A1 / A1g / A2 / A3 / A4** | Baseline; baseline plus grounding; rewriting only; the full multi-agent pipeline; the pipeline plus corrective retry. |
| **Frozen corpus** | Every arm reads the same saved documents, so a difference between arms cannot be caused by the feeds changing between runs. |
| **Exchangeability** | Arms must be comparable — differing only in the capability under test. A learning memory would break it, which is why no self-improvement rung is in this ladder. |
| **Signed-rank floor** | With only a handful of non-zero pairs, the smallest two-sided p the test can *possibly* produce is bounded. With 5 non-zero pairs it is 0.0625; with 3 it is 0.25. A normal approximation can report a number below that floor, and it is an artifact. |

**If asked**

*"Two of the p-values look significant but you call them null — why?"*
Those are the floor cases. `mrr` and `nDCG@1` for the grounding comparison have
5 and 3 non-zero pairs, so the smallest attainable two-sided p is 0.0625 and
0.25. The nominal 0.0431 and 0.1088 came from a normal approximation reporting a
value the exact test cannot reach. They are null.

*"A4 shows no effect — so retry doesn't work?"*
No, and this distinction matters. A4 returned identical documents and identical
answers on 100 of 100 questions. Retry fires below quality 0.15 and the minimum
observed was 0.300 — it never had the opportunity to act. Reporting it as
"no effect" would be a false claim; it is untested on this benchmark.

*"Why is A2 in the ladder if rewriting alone is terrible?"*
Because leaving it out would make A3 look like progress. Rewriting alone scores
0.231 against the baseline's 0.742; adding union fetch returns it to 0.761,
level with the baseline. Union fetch *repairs the damage rewriting does* rather
than improving on single-agent retrieval. Omit A2 and that reads as an
improvement.

*"If a grounded single agent matches the pipeline, why keep the pipeline?"*
On retrieval quality alone, that is a fair challenge and I would not argue with
it today. What the pipeline gives that a single agent does not is an auditable
trace — which agent did what, why a retry fired, which source backs which claim.
That is the XAI milestone in Week 9, and it is a different justification than
retrieval quality. I would rather make that argument than pretend the retrieval
number supports one.

---

## Slide 11 — The top-k sweep

**Say this**

> We suspected the paper's `k=4` configuration was throttling the architecture
> and hiding an advantage. The answer is genuinely two-sided. At k=10 we are
> *behind* by 0.088 with p = 0.0007. At k=20 we are *ahead* by 0.075 with
> p = 0.0006. Both clear zero and they point opposite ways. The mechanism is in
> the conversion numbers: the baseline packs its smaller pool into few slots very
> efficiently, and our much larger pool only dominates once given enough room.

**Terms**

| Term | Meaning |
|---|---|
| **top-k** | How many documents survive reranking and reach the answer step. |
| **Conversion** | Of the relevant documents a system *held* in its pool, what fraction it actually *shipped* in the top *k*. A ranking-efficiency measure. |
| **Matched-ceiling control** | Compare only the questions where both arms held the same number of relevant documents, which isolates ranking quality from fetch volume. |
| **Confidence interval** | The range the true difference plausibly lies in. When it does not contain zero, the effect direction is established. |

**If asked**

*"So which is it — is the architecture better or worse?"*
Both, at different *k*, and I would rather say that precisely than pick the
convenient half. `k=4` was not hiding a clean advantage. It was hiding a genuine
ranking deficit at small windows that a large enough window eventually outruns
on raw fetch volume.

*"Could this be a fetch artifact rather than ranking?"*
No — that is what the matched-ceiling control tests. At k=10 we are significantly
worse even when both arms hold an equal number of relevant documents
(p = 0.0005). By k=20 that gap is no longer significant (p = 0.10).

*"Should you change the default to k=20 then?"*
Not without measuring the cost. More documents into synthesis means more tokens,
more latency, and potentially more distraction in the answer. That is a
follow-up experiment, not a config change I would make on this evidence.

---

## Slide 12 — Grounding, seen at the endpoint

**Say this**

> This is the most concrete slide in the deck. Four real questions, and the
> "rows before" column is zero every time. The reason is a single endpoint
> behaviour: the release API matches the query against *product names*, not free
> text. "Linux" returns 606 releases. "Critical Linux updates" returns zero. A
> date-stamped sentence returns zero. So any sentence-shaped phrasing — the
> user's, the rewriter's, or a date-grounded one — retrieves nothing. That one
> fact explains the union fetch, the vendor extractor, and why a date can only
> rank results after the fetch rather than narrow them before.

**Terms**

| Term | Meaning |
|---|---|
| **Vendor extraction** | Pulling the product name out of a sentence so the endpoint has something it can actually match. |
| **Intent** | Whether the question is about a release, a security issue, a bug or community sentiment — it decides which sources are citable. |
| **Advisories excluded** | For a release question we filter out CVE advisories, so "what is the latest Linux version" is not answered with a vulnerability's affected-version string. |
| **Temporal window** | The date range "today" or "recently" resolves to. It ranks results; it cannot filter at fetch time, because the endpoint will not accept a date. |

**If asked**

*"Isn't this just working around a bad API?"*
Partly, yes — and that is a real finding about deploying RAG over live
operational feeds rather than a clean document store. Real endpoints have
matching semantics you do not control, and a rewriter that produces fluent
natural language is actively harmful against one that only matches product
names. Generic RAG advice does not tell you that.

*"Why not fix the endpoint?"*
It is not ours. Working with what the source actually does is the constraint the
system is designed around.

---

## Slide 13 — The paper: what changed, and why

**Say this**

> The conference version was an improvement claim: +17.2% on a bespoke metric,
> plus 9.3% self-improvement. The TOSEM submission is a negative result plus its
> remedy. Standard IR metrics replace the bespoke score, and the bespoke score is
> reported as superseded rather than deleted. The self-improvement figure is kept
> as mechanism-sound and magnitude-unestablished, with the drift confound stated.
> The eight-arm frozen ladder is new. And every number carries a run id, with the
> superseded figures named explicitly so nobody reintroduces them. It was
> submitted on 1 September.

**Terms**

| Term | Meaning |
|---|---|
| **TOSEM** | ACM Transactions on Software Engineering and Methodology — a top-tier SE journal. The special section is on Human–AI Collaboration in Software Engineering. |
| **Journal-first** | A track for work extending a conference paper into a journal article. Whether our workshop's proceedings status qualifies is an open question I need to confirm. |
| **Corpus drift** | The live feeds change while a run is in progress, so a system measured later sees a different corpus than one measured earlier. |
| **Confound** | Something that varies alongside the thing you are testing, so an observed difference could be caused by either. |
| **Cohen's d** | A standardized effect size — the difference expressed in standard deviations, so it is comparable across studies. d = 0.83 is large. |

**If asked**

*"Is the 9.3% self-improvement figure wrong?"*
Not wrong — unestablished. It compares time-ordered tertiles of a run against a
corpus that drifts during that run, so adaptation and drift are not separable.
The mechanism is sound and the code does what it claims; the magnitude needs a
frozen corpus or an interleaved design. That is stated in the paper rather than
quietly dropped.

*"What is still open on the paper?"*
Three things. Nobody has read the typeset PDF front to back after this much
surgery, so it may still read as a repaired conference paper rather than one
argument. Some Section 4 subsections are conference-version prose and read
unevenly. And the journal-first eligibility question needs confirming.

*"Reviewers will ask why there is no head-to-head against Self-RAG or CRAG."*
Fair, and Section 2 defends the omission explicitly rather than staying silent.
We have a reimplementation of both mechanisms over our retrieval, model held
constant, with 43 tests — its run was stopped at 8 of 100 questions, so no
results are reported. Finishing it is about 85 minutes of compute and is the
cheapest answer to that objection.

---

## Slide 14 — What cannot be quoted, and why

**Say this**

> This register is deliberate. Every figure here was once reported and is now
> void, or is real but has a condition attached. 0.973 was a pre-fix artifact —
> the correct number is 0.765. The n=96 tables came from a stalled run.
> Retrieval numbers before one specific commit are void because the fetch path
> truncated its candidate list before sorting. The mean latencies from the n=300
> run are unusable because two questions hit a host stall. And one corpus
> snapshot is no longer frozen because warm replays backfilled it. I would rather
> maintain this list than issue a correction later.

**Terms**

| Term | Meaning |
|---|---|
| **Qrels cache key fix** | The relevance cache was keyed by a question's row position, so two datasets with overlapping ids read each other's labels. Now keyed by a hash of the question text. |
| **Warm replay** | Replaying against a snapshot that is missing entries, which causes the run to fetch them live and write them back — quietly changing the snapshot you thought was frozen. |
| **Median vs mean** | The mean is dragged by extreme values; the median is not. Two questions recording 1,000–5,200 seconds because the host stalled make the mean meaningless and leave the median intact. |
| **Lower bound** | The true value is at least this — the measurement conditions can only have understated it. |

**If asked**

*"How do you know there aren't more of these?"*
I don't, with certainty. What I have is the mechanism that catches them: every
reported number maps to a run id, and `check_runs.py` re-derives whether that run
was admissible. When a number cannot be traced to an admissible run, it does not
get quoted.

*"Doesn't publishing your own errors weaken the paper?"*
The opposite, I would argue. Section 8 of the syllabus requires results to be
real and reproducible from the repository. A reviewer who finds an untraceable
number loses trust in everything; a reviewer who finds an error already named
and corrected gains it.

---

## Slide 15 — What is shipped, not just measured

**Say this**

> 629 offline tests, no network and no fixed date required — I verified that from
> a fresh clone today, installing only from the README, and it came back 628
> passed and 1 skipped. The deployment is live and I re-ran a question through it
> end to end this afternoon. Seven documentation pages live in the repo rather
> than a wiki, so a documentation change is reviewable in a pull request next to
> the code it describes. And two things are built but deliberately unreported —
> the self-reflective baseline arm, and the two ISREL bugs we fixed in it.

**Terms**

| Term | Meaning |
|---|---|
| **Self-RAG** | A published approach where the model emits critique tokens about its own retrieval and generation. |
| **CRAG** | Corrective RAG — evaluates retrieved documents and takes corrective action when they are poor. |
| **ISREL** | Self-RAG's "is this passage relevant?" critique. |
| **Failing open / failing closed** | Failing open kept a document when the critique was malformed; failing closed would discard it. Ours failed the wrong way, and both bugs narrowed the candidate set toward the critic's own preferences. |
| **Offline tests** | The suite makes no network calls and does not depend on today's date, so it produces the same result on any machine on any day. |

**If asked**

*"Why report an arm with no results?"*
Because the alternative is leaving it unmentioned, and a reviewer who finds the
code will wonder what it showed. Saying "implemented, run incomplete, no results
reported" is the honest position and it is in Section 2 of the paper.

*"629 tests for a research prototype — isn't that a lot?"*
Most of them pin behaviour that a measurement depends on. The vendor-determinism
tests exist because a nondeterministic extractor invalidated a frozen-corpus run.
The ISREL tests exist because two bugs there biased the candidate set. They are
there to stop a silent regression turning into a wrong number in a paper.

---

## Slide 16 — What comes next

**Say this**

> Four things would change a claim in this deck, in priority order. The
> independent judge is first and it is blocked — it needs an OpenAI key and has
> been waiting since 31 August. A frozen run at n=300 would make the large-sample
> result citable on its own rather than only as corroboration. Artifact packaging
> is unstarted and the snapshots are the reproducibility asset. And finishing the
> self-reflective arm is 85 minutes that answers a predictable reviewer
> objection. On the syllabus side, Weeks 6 and 7 are evaluation and benchmark
> tooling, and both are largely built already — which is why the interim report
> in Week 8 is realistic.

**If asked**

*"What do you need from me?"*
A decision on the OpenAI key. It is the one item that has been blocked for four
days and it gates the independence claim in the paper.

*"Are you on track for Week 8?"*
Yes, and the reason is that the two milestones between here and there — the
evaluation and benchmark tooling — are substantially built rather than
greenfield. The interim report is largely a matter of writing up what
`FINDINGS.md` and `PROVENANCE.md` already contain.

---

## Questions that could come at any point

**"What is the contribution, in one sentence?"**
A concrete, measured failure mode in query rewriting for RAG — rewriting that
replaces rather than augments the user's query destroys recall at fetch time —
together with a cheap fix and an evaluation harness that can tell grounding
apart from coordination.

**"Would you build it this way again?"**
I would ground the question first and add coordination only where an auditable
trace is worth the latency. The evidence says the understanding step is what
pays, and I did that work last rather than first.

**"How much of this is your own analysis?"**
All of it, and I can walk through any number's derivation on request — that is
what the run ids are for. AI assistants were used for coding and drafting, which
the paper's "Use of AI tools" statement records.

**"What are you least confident about?"**
The judge. Every answer-quality number in this deck was produced by a model that
shares a family with one of the systems it scored. I do not think it changes the
retrieval conclusions, because retrieval metrics do not involve the judge at all
— but I cannot say that about faithfulness until Phase 4 runs.

**A question I should not bluff on:** anything about absolute performance against
a published system. We have no head-to-head numbers against Self-RAG or CRAG.
The correct answer is that the arm exists, the run is unfinished, and I will have
it before the interim report.
