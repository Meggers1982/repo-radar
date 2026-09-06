---
title: "Three tools I actually installed this month"
subtitle: "What they claim, what happened, and where each one broke"
date: "September 2026"
---

# Three tools I actually installed this month

Most roundups of AI and agent tooling are written from README files. This one isn't. Each
of the three below was installed on a working machine, pointed at real material rather
than the sample data that ships with it, and run until something went wrong. The part
where it went wrong is the part worth your time — it's the only section nobody who
skimmed the repo can write.

A note on scope, up front: this is the first of these, and it covers three tools rather
than the five or six a monthly roundup should carry. That's an honest constraint, not an
editorial choice.

## Datasette — the one that paid for itself in an hour

**What it claims:** publish any dataset as an explorable, queryable website.

**What happened:** I pointed it at every US food recall the FDA has reported since 2020 —
10,161 records, pulled from a public API and loaded into a database with a single command.
Within the hour it had produced a number I haven't seen published anywhere.

The `state` field on an FDA recall is the *recalling firm's headquarters*. It is not where
the food went. Where the food went lives in a free-text field with 2,561 distinct values
across those 10,161 records.

For Nebraska, the gap is this:

- 14 recalls list a Nebraska firm
- 2,842 recalls actually reached Nebraska, once you count both the ones that name the state
  and the ones distributed nationwide

That's a factor of 203. Any "food recalls by state" map built on the obvious field — the
one called `state` — understates local exposure by more than two orders of magnitude. The
same trap sits in every state in the country: recalls distributed nationwide alone are 15%
of the total, and the states that top the list by firm headquarters are simply where large
food companies are incorporated.

**Why it matters commercially:** the output of an install like this is a *finding*, not a
tool review. A finding is a bylined piece with a number in it that nobody else has. That's
a different and better product than a post about software.

**Where it broke:** not in Datasette. The API it was reading returns a 404 rather than an
empty result once you page past the end of the data, so the obvious loop — keep fetching
until you get nothing back — crashes on the final page and loses everything already
collected. It cost me the first 3,887 records before I noticed.

## journalism-core — a checklist that caught me being wrong

**What it claims:** fifteen skills for reporting, verification and publishing, built for
newsrooms rather than for developers.

**What happened:** the interesting test wasn't running it on a sample. It was pointing its
data-journalism validation checklist at the recall analysis above, which I had already
written down as finished.

One item on that checklist — test whether your result survives a reasonable change to your
definitions — caught a real error. My first pass at finding Nebraska in that free-text
field matched on the state abbreviation surrounded by spaces. That silently misses every
record written as `MO, NE, NH`, because there the abbreviation is followed by a comma. A
stricter match found 948 more records, and moved the headline figure from 136× to 203×.

A 49% swing in a published number, from a single definition I hadn't questioned.

**Why it matters commercially:** the value here isn't that the software is clever. It's
that a checklist caught something a person had already signed off on, in an analysis
intended for publication. That's cheap insurance on the one thing you can't afford to get
wrong.

**Where it broke:** two of the fifteen skills are weaker than the rest. One is a banned-word
list — delve, realm, tapestry — which restates judgement any editor already applies. More
awkwardly, its generic fact-checking skill overlaps a more specific one I already run,
which checks claims against re-fetched source abstracts. Two tools that fire on the same
trigger and give different advice is a real cost, not a neutral. Install the parts you'll
use; the ability to take fifteen at once is not a reason to.

## Remotion — works exactly as advertised, and I still can't justify it

**What it claims:** build videos out of React components, so that a video becomes a build
artifact a pipeline can regenerate whenever the underlying data changes.

**What happened:** I fed it a live data file from a project of mine and had it render a
1080×1350 social card as an eleven-second video. Total render time: under seven seconds.
Change the data, run one command, get a new video. The claim is straightforwardly true.

**Why it matters commercially:** it removes the second creative process. Ordinarily a chart
becomes a video by someone rebuilding it in a video tool. Here the chart and the video are
the same source, so publishing a recurring visual costs roughly what publishing the data
costs.

**Where it broke:** twice, and the two failures are instructive in opposite directions.

The first is a trap. Its sequencing component silently wraps whatever you give it in a
full-screen container unless you pass a specific flag. Miss the flag and every element
covers everything before it — you get one card floating in an empty frame. Nothing errors.
It renders "successfully" and looks wrong, which for something a pipeline produces
unattended is the worst possible failure.

The second is the opposite, and to Remotion's credit. Pointing the same template at an
older data file crashed on the very first frame, because that older file was written before
a field existed. Loud, immediate, impossible to miss. For an unattended build step, that is
exactly right — and it surfaced a real bug in my own data format that a dashboard reading
the same file would have hit eventually.

**The honest verdict:** it does what it says, quickly, and I have no standing reason to
produce video on a schedule. It stays installed. It doesn't become part of the business
until there's a series that wants a recurring visual.

## What the month actually taught me

Two of these three are keepers, and only one changes what I sell.

The pattern worth noticing is that the tool which paid off wasn't the most impressive one.
Remotion is the more sophisticated piece of engineering by some distance. Datasette is
older, plainer, and produced a publishable number in an afternoon — because it happened to
sit next to a question I already had.

That's the whole argument for installing against your own material rather than the sample
data. The sample data will always work. It's designed to. What you learn from it is whether
the demo runs, which you already knew.
