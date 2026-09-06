# The Friction List

Section 2 of the strategy doc, MEA-63. Every time something in your own work is
tedious, slow, or manual, one line about it, tagged with a lane. The list is a query
queue with a guaranteed-relevance property: it can only contain problems you
actually have.

**Status: DRAFT — these are not yet your lines.**

The ticket says this is the one thing Claude can't do for you, and that's right about
the *judgment*. But it isn't right that the page has to start blank. What follows is
twelve candidate lines reverse-engineered from your own project history — things that
have actually gone wrong more than once across the repos and routines. Your job is to
cut the ones that aren't real friction for you, fix the wording on the ones that are,
and add what's missing. That's a twenty-minute edit, not a blank hour.

Phrase each line as **concrete technical nouns**, not as the problem in the abstract.
That is what `ghfriction` needs — it ANDs unquoted terms against README text, so
"merge place records" finds nothing and "entity resolution address matching" finds
the tool.

---

## Candidate lines

Each was run through `ghfriction` on 2026-09-06. The verdict column is what the
channel actually returned, not what it should have returned.

| # | Lane | The friction | Query terms | Verdict |
| -- | -- | -- | -- | -- |
| 1 | 7 | Merging place records across sources without duplicates | `entity resolution address matching deduplication` | **Hit** — zinggAI/zingg |
| 2 | 9 | Government dataset to a defensible number without a manual clean cycle | `government data cleaning csv` | **Hit** — PUDL, practical-sql-2 |
| 3 | 8+10 | Clean transcript with speaker labels from a recorded interview | `speaker diarization transcript` | **Hit** — WhisperLiveKit, FunClip |
| 4 | 5 | A scheduled job stops producing and nothing tells me | `cron job monitoring dead mans switch alerting` | **Hit** — bdd/runitor, ptweezy/cronstable |
| 5 | 5 | A write reports success but nothing actually landed | `api client retry idempotent write verification` | Weak — julep is adjacent, rest is noise |
| 6 | 5 | A routine re-reads the same inbox and files the same thing twice | `idempotent email processing deduplicate messages` | Miss |
| 7 | 3 | The same fix applied by hand across N near-identical repos | `sync files across multiple repositories template` | Miss |
| 8 | 4 | Porting a project silently bumps major versions | `detect dependency version drift lockfile` | Weak — cdxgen (SBOM) is the near miss |
| 9 | 6 | A stale year or place name left outside the config block | `detect hardcoded values configuration audit` | Miss |
| 10 | 6 | Enforcing a voice spec at draft time rather than at review | `prose style linter writing rules enforce` | Miss |
| 11 | 2+6 | Keeping shared stats in sync across many briefs | `single source of truth content transclusion` | Miss — returns nothing after filtering |
| 12 | 6 | Detecting when a year reference in a title has gone stale | `content freshness audit outdated pages` | Miss |

Lines 1, 2, 3 and 10–12 are the six starters from the ticket. Lines 4–9 are new,
drawn from failures recorded across the routines, the digest estate, the Paper Trail
port and the receipt-filing work.

## What the run actually taught

**Four of twelve lines produced a usable repo.** That is a real hit rate for this
channel and better than the scored lanes managed on the same day.

**The hits and misses split cleanly, and not by how real the problem is.** Lines 1–4
name a field that already has a name — entity resolution, diarization, dead-man's-switch
monitoring. Lines 5–12 describe a workflow, and no one writes a README in workflow
terms. The failing lines are not less painful; they are less *named*. Where a line
misses, the useful next move is usually to find the term of art rather than to
rephrase the complaint.

**A junk filter had to be added before the results were readable.** `jbranchaud/til`
came back first for three unrelated queries — a 14k-star "Today I Learned" log
contains every word, so it matches any ANDed term set and wins on stars. Second-brain
vaults, boilerplate collections and `learning-zone/*-basics` course repos do the same.

That could not be fixed inside the query: **GitHub search caps a query at five
AND/OR/NOT operators, and `GHFRICTION_NOT` already spends all five.** A sixth `NOT`
returns HTTP 422 Validation Failed. So the filter now runs client-side after the
fetch, as `GHFRICTION_DROP` in `scripts/lane-queries.sh` — the same approach
`global_excludes` takes in `radar.py`. Verified: it removes the catch-alls and leaves
the diarization and government-data results untouched.

## How to work the list

1. Edit the table. Cut what isn't yours, reword what is, add what's missing.
2. Run `ghfriction "<terms>"` on each surviving line.
3. On a miss, try the term of art rather than the complaint.
4. Star everything you screen, either way — that is what feeds section 4B.
5. Keep the verdict column honest. A line that misses three times is telling you the
   tool doesn't exist, which is its own useful answer.
