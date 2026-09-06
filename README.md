# repo-radar

Standing GitHub queries for a five-lane interest map, scored and deduplicated into a
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
| Monthly | 1st, 13:00 UTC | All five |

GitHub cron is UTC and does not follow DST, so the local time shifts by an hour twice a
year. Each lane's `"cadence"` field decides which run it belongs to.

## Lanes

Five live lanes: **1** agent harnesses and agent design, **2** content and SEO tooling,
**5** personal and business automation, **8** journalism and reporting workflow,
**9** data journalism.

It was ten until 2026-09-06. Once the scoring fix above made lane yield mean something,
simulating `guaranteed_per_lane: 0` so the lanes competed for all 24 slots showed that
lanes 3 (research digests), 4 (web builds), 6 (writing workflow), 7 (place-based research)
and 10 (AI video) earned **zero** — lane 10 had no qualifying candidate leading it at all.
They had only ever appeared in a report because the per-lane floor handed them two slots
each. They are kept in `retired_lanes` in `config/lanes.json`, so restoring one is a matter
of moving its object back into `lanes`; `radar.py` reads `lanes` only.

Cutting a lane removes the *standing query*, not the subject. `scripts/lane-queries.sh`
still carries `ghdigest`, `ghsanity`, `ghwriting`, `ghgeo` and `ghvideo` as hand tools, and
`ghfriction` covers the same ground on demand — it is where zingg (place records) and
WhisperLiveKit (transcripts) actually came from, not from lanes 7 and 10.

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
ghfriction "speaker diarization transcript"           # search READMEs by problem
```

`ghfriction` is the friction-list channel and it is **not** an exact-phrase search.
Quoting the whole sentence returns zero — no README is written in your words. Phrase it
as concrete technical nouns and the terms are ANDed, under a star ceiling and a NOT list
that keep awesome-lists and roadmaps out:

```bash
ghfriction "government data cleaning csv"       # -> PUDL, practical-sql-2
ghfriction "speaker diarization transcript"     # -> WhisperLiveKit, FunClip
ghfriction "<terms>" <min-stars> <max-stars>    # defaults 50 and 20000
```

## Dashboard

`docs/index.html` is the reading surface: a static page, no build step, served from
`/docs` by both GitHub Pages and Vercel.

A **run log** down the left side keeps every run the data file still holds — date,
cadence, how many surfaced, how many were new, and how many of that run's repos have
since been saved or dismissed. Clicking one loads it. Runs stay in the log until they
fall out of the 52-run window `radar.py` keeps.

Every card carries **Save** and **Dismiss**:

- **Save** keeps a repo in the Saved collection, which is the shortlist that survives
  the run scrolling away. A save stores a copy of the card, not a pointer to it, so a
  kept repo stays readable after its run drops out of the window.
- **Dismiss** hides a repo from every run view and files it under Dismissed, where it
  can be restored. Dismissals are undoable for twelve seconds after the click.

Saving and dismissing are opposites: doing one clears the other.

### Where that state lives

Saves and dismissals persist in **Neon Postgres**, through a serverless function at
`/api/state`. They follow the account, not the browser: save something on the laptop,
it is there on the phone.

```
repo_state
  full_name   text primary key     owner/repo
  status      text                 'saved' | 'dismissed'
  run_id      text                 the run it was saved from
  snapshot    jsonb                the card, so a save outlives its run
  updated_at  timestamptz
```

One row per repo, not two tables, because saved and dismissed are opposite states of
the same repo rather than independent flags — which makes "saving clears the dismissal"
a plain upsert.

The header says which mode the page is in:

- **saved to the database** — the Vercel deployment, where `/api/state` exists.
- **this browser only** — the GitHub Pages copy, which has no backend and falls back to
  `localStorage` under `repo-radar:v1`. Anything saved there is pushed up to the
  database once, on the next load of the Vercel copy; rows already in the database win.

Writes are optimistic: the card updates immediately, and if the write is rejected the
screen rolls back and says so rather than showing a save that did not happen.

`ledger/seen.json` is still the durable record of what has ever been *scored*. Saved and
Dismissed are a reading layer on top of it.

### Access

**`/api/state` has no auth of its own.** What keeps it private is Vercel Deployment
Protection, which is on. Turning it off would put read *and write* on a public URL, so
add auth to the function first if the dashboard ever needs to be public. (The GitHub
Pages copy is public, but it is read-only by construction — no API, no database.)

Setting up a fresh database:

```bash
vercel integration add neon --name repo-radar-db --plan free_v3 -m region=iad1 -m auth=false
vercel env pull .env.local
npm install
node --env-file=.env.local scripts/db-init.mjs   # creates repo_state, safe to re-run
```

## English only

A repo whose description is mostly non-Latin script is dropped, **unless the repo ships
an English README in its root** (`README.en.md`, `README_EN.md` and friends) — at which
point the translation already exists and the repo is kept, flagged `translated:` in the
report and with an `english readme` chip on the dashboard.

The test is a script test, not a language test, and it runs on the description, because
the description is what the report prints and what Gate 1 is skimmed from. Consequences
worth knowing:

- Bilingual descriptions — an English tagline beside a native one — pass, which is the
  common and correct case.
- Spanish, German and Indonesian repos pass. They are readable at a skim, and Gate 1 is
  a skim, not a translation exercise.
- A repo with an unreadable description but English topic tags does *not* coast through
  on the tags. It gets checked for a translation like any other.

Only repos that would otherwise have surfaced are checked, and `english_check_limit`
caps how many root listings a single run will fetch, so the gate costs a handful of
requests rather than one per search result. Turn the whole thing off with
`"require_english": false`; `english_min_share` is the share of letters that must be
Latin, default `0.6`.

## Layout

```
config/lanes.json      the five live lanes plus retired_lanes: topics, queries, orgs, weights, excludes
scripts/radar.py       search, score, dedupe, report
scripts/seed_ledger.py mark already-starred repos as seen
scripts/lane-queries.sh shell functions for ad-hoc searches
ledger/seen.json       every repo ever scored; a repo surfaces once, ever
outputs/               one markdown report per run
docs/index.html        static dashboard: run log, Saved and Dismissed
docs/data/index.json   the last 52 runs, picks and all
api/state.js           reads and writes Saved/Dismissed in Neon
scripts/db-init.mjs    creates the one table the dashboard needs
vercel.json            static deploy config: no build, output directory is docs/
```

`radar.py` uses the standard library only, so there is no `requirements.txt`. Keeping an
empty one made Vercel detect the repo as a Python app and fail the build looking for an
entrypoint; `vercel.json` pins the deploy to `docs/` with no build step. The one npm
dependency is the Neon driver, used by `api/state.js` and nothing else — the radar
pipeline itself still installs nothing and calls no LLM.

## How scoring works

```
score = merit × star_weight × freshness × lane_weight × lane_bonus × org_bonus + growth
        where merit      = max(velocity, standing)
              lane_bonus = max(multi_lane, crossover)
```

- **velocity** — `log10(1 + stars/day × 30)`, capped at `velocity_cap`. Age-relative
  popularity, not raw popularity: 500 stars in six weeks beats 40,000 stars from 2021.
  The cap is 2.5, about 316 stars a month. It was 4.0 — 10,000 a month — and at that
  height every viral general-audience repo pinned it, so the lane weights and crossovers
  below never got to decide anything.
- **merit** — `max(velocity, standing)`, two readings of the same repo. **velocity** is
  log-damped monthly star rate: age-relative popularity, so a three-month-old repo with
  5,000 stars is news. **standing** is `standing_weight × log10(1 + stars)`, and a lane
  sets it when its best work is finished rather than growing. Lanes 8 and 9 use 0.5; lane 1
  stays at 0 on purpose, because there a star count measures the size of the audience
  rather than the quality of the harness. A repo qualifies on either, and needs only one.

  Velocity alone buried exactly the tools those lanes were built for: `alephdata/aleph`
  ranked #124 and `opensanctions` #94, and with them `pdfplumber`, `csvkit`,
  `sqlite-utils`, `dangerzone` and `securedrop` — all from the followed org list, all old,
  modestly-starred and maintained rather than abandoned. Lane 9's `freshness_floor` was
  written for this case and could not reach it, because it corrects time-since-push and
  not the growth term. Tuned on the 2026-09-06 pool: 0.4 barely moved anything, 0.6 gave
  lanes 8 and 9 seventeen of the twenty-four slots.
- **star_weight** — from the *lead* lane. Lane 1 sets 0.6 because "AI agents" is the most
  crowded topic on GitHub, and its star counts measure the size of the audience rather than
  the quality of the harness.
- **freshness** — decays over a year, down to a per-lane floor. Lane 9's floor is 0.7,
  because data journalism tools are often finished rather than abandoned.
- **lane_bonus** — `max(multi_lane, crossover)`, never the product. A repo matching two
  lanes outranks a stronger repo matching one, and a configured pair can be worth more
  still. The two used to be multiplied, which billed the same observation twice: a 1+9
  pair took 2.4× and a four-lane repo 4.0×, against a lane weight that only spans 1.0–1.3.
  Every one of the top 24 was multi-lane and the best single-lane specialist ranked #31.
  `multi_lane_step` is 0.35 capped at `multi_lane_cap` 2 extra lanes, so a repo cannot buy
  rank by tagging itself into five subjects. Consequence: a crossover at or below the
  generic two-lane value (1.35) never fires — `scripts/lane-overlap.py` reports which.
- **growth** — stars gained since a previous run saw it but did not surface it.

### Strong vs. weak lane evidence

A lane match is **strong** when the maintainer's own topic tag or the owner org says so,
and **weak** when only a keyword appeared in the name or description. Only strong evidence
earns a crossover multiplier. Several lanes legitimately share vocabulary — "transcription"
belongs to both journalism and video — and treating those as equal produced fake crossovers
that pushed TTS repos into the journalism lane on the first tuning run.

Weak-only matches are held to a higher bar in two places: they can never take one of a
lane's `guaranteed_per_lane` slots, and they must clear `weak_min_score` (2.5) rather than
`min_score` (1.5). A guaranteed slot is meant to stay empty rather than be filled with
noise.

### Orgs are searched, not just scored

A lane's `orgs` list feeds the 1.25× score bonus. It does **not** feed discovery — only
the strings in `queries` are ever sent to the search API. Lanes 8 and 9 originally listed
`simonw`, `alephdata`, `opensanctions`, `wireservice`, `jsvine` and `palewire` for the
bonus alone, which meant datasette, sqlite-utils, aleph, followthemoney, csvkit, agate and
pdfplumber could only appear if they happened to match a topic query — and none of them
did. Each followed account that matters now has its own `org:` query. GitHub search accepts
`org:` for user accounts too, so `org:simonw` and `org:jsvine` work unchanged.

### Hard excludes, not soft penalties

Interview-prep repos, roadmaps, cheat sheets, and awesome-lists are excluded outright
rather than scored down, because a soft penalty never actually keeps them out. Trading and
investing tools are excluded on the same grounds: nothing in the lanes is about
equities, but an investing workbench tags itself `mcp`, `ai-agents`, `research-assistant`
and `nextjs`, stacks four strong lanes, and lands at the top of the run. The pattern names
instruments and strategies rather than "finance", so financial-accountability reporting
tools in lanes 8 and 9 still come through. Lane 10
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

## Release radar

`feeds/release-radar.opml` is section 4C: an OPML file of `releases.atom` feeds for the
tools already in use, grouped by area. Import it into any reader. This answers a different
question from discovery — not "what exists" but "did something I already trust just grow
the feature I'd given up on".

The repos were chosen from what this machine's projects actually depend on, not from a
generic list, and every feed was checked for a 200 and a non-empty entry list before being
added. Two are worth knowing about: `opensanctions/opensanctions` last tagged a release in
2023 and `Zulko/moviepy` in 2025, so both ship from `main` rather than through GitHub
Releases and the feed will stay quiet.
