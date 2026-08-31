# Specs

Read in this order. Each file answers one question and hands off to the next.

| File | Question it answers |
|---|---|
| [`mission.md`](mission.md) | Why this project exists, what we claim, what would falsify each claim, and where the work honestly stands |
| [`tech-stack.md`](tech-stack.md) | With what — locked versions, models, endpoints, environment variables, repository map |
| [`pipeline.md`](pipeline.md) | How it is wired — execution graph, the two fixed defects, data contracts, failure policy, cost |
| [`evaluation-protocol.md`](evaluation-protocol.md) | How it is measured — datasets, qrels and pooling bias, metrics, arms, admissibility, statistical plan, threats |
| [`roadmap.md`](roadmap.md) | In what order — phases 0–8, each with commands, a definition of done, and a gate |
| [`reproducibility.md`](reproducibility.md) | How a stranger reproduces it — ACM artifact badges, what gets archived, clean-clone rehearsal |
| [`writing.md`](writing.md) | How it gets published — paper structure, figures, AI disclosure, integrity practice, checklist |

Two conventions hold across all of them.

**Claims are falsifiable.** `mission.md` §3 states what evidence would kill each
claim. If a run produces that evidence, the claim changes — the run does not.

**A number without provenance is not a result.** Every reported figure traces to a
`results/<run_id>/` directory whose `config.json` proves which arm ran, on which
corpus, judged by what. `evaluation-protocol.md` §5 is the checklist that decides
whether a run may carry a claim at all.
