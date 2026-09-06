# Ten-Lane Map Review — 2026-09-06

Written for MEA-64 ("Confirm or Prune the Ten-Lane Map"), after MEA-65's all-lane
tuning run produced the first output worth judging the map against.

**Evidence base:** two weekly runs (2026-09-02, 2026-09-06) and one all-lane dry run
(2026-09-06), plus `outputs/gate1-screen-2026-09-06.json`.

## The finding: the map is not the problem, lane 1 is

MEA-64 asks which lanes to cut. On the evidence, none — because no lane has been
given a fair test yet. Lane 1's vocabulary matches nearly every repo in every other
lane, so cross-lane signal is currently meaningless.

Share of each lane's picks that were *also* matched by lane 1:

| Run | Lane 2 | Lane 5 | Lane 6 | Lane 9 | Lane 10 |
| -- | -- | -- | -- | -- | -- |
| 2026-09-06 weekly | 5/6 | 6/6 | — | — | — |
| 2026-09-06 all (dry) | 3/3 | 5/5 | 2/2 | 2/2 | 2/2 |

Lane 1's topics are `ai-agents`, `mcp`, `agent`, `agentic`, `llm-agent`,
`agent-framework`. In September 2026 those tags are on essentially every AI-era
repo regardless of what it does. Lane 1 has stopped being a lane and become a
universal matcher.

### This compounds through the crossover multipliers

`crossovers` treats a lane-1 match as evidence of a rare and valuable overlap:

```
"1+9": 1.6,   # "the rarest skill overlap"
"1+10": 1.4,
"1+2": 1.3,
```

If lane 1 matches everything, these fire on almost everything, and the largest
multiplier in the config boosts exactly the generic repos it was written to
de-prioritize. Observed in the all-lane run: **OtterMind/Chat2DB — a database
client — took the 1+9 "rarest skill overlap" 1.6× multiplier** and led lane 1.

### What lane 1 actually returned

The 2026-09-06 weekly picks, in score order:

| Repo | Stars | What it is |
| -- | -- | -- |
| siyuan-note/siyuan | 46k | note-taking app |
| ui-ux-pro-max-skill | 125k | UI/UX design skill pack |
| Panniantong/Agent-Reach | 78k | social-media scraper CLI |
| career-ops-hq/career-ops | 70k | AI job-search tool |
| n8n-io/n8n | 203k | workflow automation platform |
| open-webui/open-webui | 151k | chat UI |

None is about agent harnesses or agent design, which is what lane 1 is for. All six
are megarepos, despite `star_weight: 0.6` and `velocity_cap` having been lowered
from 4.0 to 2.5 on 2026-09-06 for precisely this reason. The cap change did not fix
it.

Lanes 1 and 5 are also not separable as written — n8n and activepieces are the same
kind of tool arriving in both.

## Why no lane can be cut yet

`max_candidates_total: 24` with `guaranteed_per_lane: 2` across ten lanes means 20
of 24 slots are allocated by the floor before quality is consulted. The all-lane run
returned **exactly 2 picks for every lane except 2 and 5**, which split the 4 spare
slots. Every pick cleared `min_score: 1.5` comfortably (lowest was 3.18), so nothing
was scraping in — but nothing was competing either. The cap structure, not lane
quality, decided the distribution.

The ticket's cut rule is "cut any lane that hasn't produced work in six months."
The pipeline has produced output on three days. That rule cannot be applied yet, and
cutting on this much data would be guessing.

## Recommendation

1. **Cut nothing today.** Lanes 3, 4, 6, 7 were named as likely cuts; there is no
   evidence for or against them, because they have never run against a fair budget.
2. **Fix lane 1 first**, then re-judge the map. Two changes worth trying:
   - Narrow lane 1's topics to terms that still discriminate — `claude-code`,
     `agent-framework`, `multi-agent`, `agentic-workflow` — and drop the bare
     `agent`, `ai-agents`, `mcp`, `llm-agent`, which now match the whole field.
   - Make crossover multipliers conditional on lane 1 matching by *topic or org*
     rather than by keyword, so a passing mention of "agentic" in a README does not
     earn the 1.6×.
3. **Then raise `max_candidates_total`** for one all-lane run — or drop
   `guaranteed_per_lane` to 0 — so lanes have to earn their slots. One run under
   those conditions gives a real basis for pruning.
4. **Re-run this review after that.** Cutting lanes is a decision about Meagan's
   interests and stays hers; this document only establishes that the current output
   is not yet evidence about them.

## Not addressed here

Lane 2 returned six near-identical "skills pack" repos on 2026-09-06 (opc-skills,
claude-skills, affiliate-skills, digital-marketing-pro, GEOFlow). That is a single
genre flooding a lane rather than a lane-definition problem, and it may resolve on
its own; noting it so the next review can check whether it recurred.
