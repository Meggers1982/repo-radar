# repo-radar

Standing GitHub queries for a ten-lane interest map, scored and deduplicated into a
weekly shortlist. Implements the discovery half of *GitHub Repo Discovery Strategy*.

The problem it solves: repo discovery is otherwise passive, and general trending lists
are aimed at a general audience. This runs the queries for the lanes I actually work in
and hands back ten to twenty candidates a week to screen.

**No LLM calls anywhere in the pipeline.** GitHub's search API plus deterministic scoring
does the whole job, so it runs on the `GITHUB_TOKEN` that Actions provides for free, needs
no configured secrets, and cannot be blocked by an API balance.

## Cadence

| Run | When | Lanes |
|---|---|---|
| Weekly | Mondays 13:00 UTC | 1 agents, 2 content/SEO, 5 automation, plus the velocity query |
| Monthly | 1st, 13:00 UTC | All ten |

GitHub cron is UTC and does not follow DST, so the local time shifts by an hour twice a
year. Each lane's `"cadence"` field decides which run it belongs to.

## Use

```bash
export GITHUB_TOKEN=$(gh auth token)

python3 scripts/radar.py --cadence weekly      # fast lanes
python3 scripts/radar.py --cadence monthly     # everything
python3 scripts/radar.py --lane 9 --dry-run    # one lane, no writes
python3 scripts/seed_ledger.py                 # mark starred repos as already seen
```

`--dry-run` prints the report without touching `outputs/`, `ledger/`, or `docs/`. Use it
when tuning a query.

Interactive versions of the same queries, for when a question comes up between runs:

```bash
source ~/repo-radar/scripts/lane-queries.sh

ghvelocity          # young and already popular
ghagents ghmcp      # lane 1
ghdatajourn         # lane 9
ghorg propublica    # sweep one org
ghfriction "merge place records without duplicates"   # search READMEs by problem
```

## Layout

```
config/lanes.json      the ten lanes: topics, queries, orgs, weights, excludes
scripts/radar.py       search, score, dedupe, report
scripts/seed_ledger.py mark already-starred repos as seen
scripts/lane-queries.sh shell functions for ad-hoc searches
ledger/seen.json       every repo ever scored; a repo surfaces once, ever
outputs/               one markdown report per run
docs/                  static dashboard (GitHub Pages and Vercel both serve /docs)
vercel.json            static deploy config: no build, output directory is docs/
```

`radar.py` uses the standard library only, so there is no `requirements.txt`. Keeping an
empty one made Vercel detect the repo as a Python app and fail the build looking for an
entrypoint; `vercel.json` pins it to a plain static deploy of `docs/`.

## How scoring works

```
score = velocity × star_weight × freshness × lane_weight × multi_lane × crossover × org_bonus + growth
```

- **velocity** — `log10(1 + stars/day × 30)`, capped. Age-relative popularity, not raw
  popularity: 500 stars in six weeks beats 40,000 stars from 2021.
- **star_weight** — from the *lead* lane. Lane 10 sets 0.35 because star counts there are
  inflated by an audience chasing volume output.
- **freshness** — decays over a year, down to a per-lane floor. Lane 9's floor is 0.7,
  because data journalism tools are often finished rather than abandoned.
- **multi_lane / crossover** — a repo matching two lanes outranks a stronger repo matching
  one. Configured pairs get an extra multiplier; 1+9 is the highest at 1.6.
- **growth** — stars gained since a previous run saw it but did not surface it.

### Strong vs. weak lane evidence

A lane match is **strong** when the maintainer's own topic tag or the owner org says so,
and **weak** when only a keyword appeared in the name or description. Only strong evidence
earns a crossover multiplier. Several lanes legitimately share vocabulary — "transcription"
belongs to both journalism and video — and treating those as equal produced fake crossovers
that pushed TTS repos into the journalism lane on the first tuning run.

### Hard excludes, not soft penalties

Interview-prep repos, roadmaps, cheat sheets, and awesome-lists are excluded outright
rather than scored down, because a soft penalty never actually keeps them out. Lane 10
carries its own exclude for the volume-output genre: faceless-channel tooling, shorts
generators, "videos per day", auto-uploaders. The lane's test is whether a tool gives more
control over material you already have, not whether it produces more output.

## Tuning before automating

Run a lane with `--dry-run`, read the output, edit `config/lanes.json`, run again. Only
turn on the schedule once the queries return things worth screening. Query dates use
`{d-N}` macros that expand to N days before the run, so nothing goes stale.

## Ledger

`ledger/seen.json` records every repo ever scored, with the stars it had when first seen.
A repo that surfaces is marked and never surfaces again. Seeding from starred repos means
anything already looked at stays out — which is the reason Gate 1 says to star everything
screened, rejects included.
