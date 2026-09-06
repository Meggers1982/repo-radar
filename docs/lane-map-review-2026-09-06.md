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

---

# Addendum, same day: the lane-1 diagnosis above was wrong

Acting on it turned up better evidence. Recorded here rather than edited away,
because the wrong version was already in MEA-64 and MEA-239.

## What the measurement actually says

`scripts/lane-overlap.py` (new) fits every repo returned by every lane query
against the lane definitions and reports pairwise overlap. On 844 repos fetched
2026-09-06, of which 737 fit at least one lane:

```
lane   claims  strong   share
1         219     209    28%
8         179     156    21%
9         157     154    21%
5         106     106    14%
```

**No lane pair exceeds 50% overlap. The lanes are separable.** Lane 1 claims the
largest share at 28%, which is a big lane, not a universal matcher. The crossover
multipliers fire on 1–6% of the pool, not on almost everything.

The "100% of lanes 5/6/9/10's picks were also lane 1" figure in the section above
is real but was measured on the 24 *picks*, not on the pool they were drawn from.
That is a selection effect, and mistaking it for a property of lane 1 was the error.

## The actual defect: the multi-lane bonus was billed twice

```
multi_lane = 1.0 + 0.5 * (strong_lanes - 1)      # uncapped
crossover  = up to 1.6
score      = ... * multi_lane * crossover * ...   # both, multiplied
```

Both terms are paid for the same observation — that the repo sits in more than one
lane — so they compounded. A 1+9 pair earned 1.5 × 1.6 = 2.4×; a four-lane repo
earned 4.0×. Nothing else in the formula moves that far: lane weight spans 1.0–1.3
and `star_weight` 0.6–1.0. The bonus was deciding the ranking by itself.

Measured on the pool: **all 24 top-scoring repos were multi-lane. The best
single-lane specialist — `simonw/llm`, from a followed org — ranked #31.**
`simonw/datasette` ranked #63. Only 213 of 698 scored repos were multi-lane at all,
so 31% of the pool was taking 100% of the top.

Lane 1 was the most common ingredient in a winning stack simply because it is the
biggest lane. That is why the symptom looked like a lane-1 problem.

## Fix

`score_repo` now takes `max(multi_lane, crossover)` rather than the product, and the
increment is `multi_lane_step: 0.35` capped at `multi_lane_cap: 2` extra lanes, both
in `settings`. Measured effect on the same pool: best single-lane specialist moves
**#31 → #13**.

Consequence worth knowing: a crossover is now the bonus *for that pair* rather than a
surcharge on top of the generic one, so any entry at or below the generic two-lane
value (1.35) never fires. As of today that is `1+2`, `8+9` and `8+10`.
`lane-overlap.py` flags them.

## Tested and rejected: narrowing lane 1's topics

Restricting lane 1 to `claude-code`, `agent-framework`, `agentic-workflow`,
`multi-agent` and dropping the bare `ai-agents` / `mcp` / `llm-agent` removed lane 1
from the top 24 **entirely** (0/24) and pushed the best specialist back from #13 to
#20. It does not improve precision, it just deletes the highest-weighted lane.
Not applied. Recommendation withdrawn.

## What this means for pruning (MEA-64)

With the scorer fixed, simulating `guaranteed_per_lane: 0` so lanes compete for all
24 slots:

| Lane | Slots earned | Candidates in pool | Best score |
| -- | -- | -- | -- |
| 1 Agents | 9 | 166 | 4.14 |
| 5 Automation | 5 | 33 | 5.10 |
| 2 Content/SEO | 4 | 18 | 4.94 |
| 9 Data journalism | 4 | 42 | 4.11 |
| 8 Journalism | 2 | 12 | 4.22 |
| 3 Digests | 0 | 3 | 3.23 |
| 4 Web builds | 0 | 17 | 3.11 |
| 6 Writing | 0 | 15 | 3.25 |
| 7 Place-based | 0 | 19 | 2.50 |
| 10 AI video | 0 | **0** | — |

Lanes 3, 4, 6, 7 and 10 earn nothing when they have to compete — they appear in the
report only because `guaranteed_per_lane: 2` hands them slots. Lane 10 has **zero**
qualifying candidates leading it at all, which is worth noting against the original
assumption that lanes 8/9/10 were promising-but-untested; 8 and 9 hold their own, 10
does not.

This is one snapshot and still not six months of evidence, so it is not yet grounds
to cut. It does say the ticket's original guess — "lanes 3, 4, 6, 7 are the likeliest
cuts" — is pointing the right way, and that lane 10 belongs on that list.
