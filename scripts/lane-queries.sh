#!/usr/bin/env bash
# repo-radar lane queries for interactive use.
# Add to ~/.zshrc:   source ~/repo-radar/scripts/lane-queries.sh

# Third arg is an extended-regex applied to "name<TAB>description" and dropped if
# it matches. Client-side, because GitHub search caps a query at five AND/OR/NOT
# operators -- GHFRICTION_NOT already spends all five, and a sixth returns
# HTTP 422 Validation Failed. Junk filtering cannot grow inside the query.
_gh_repo_search() {
  local q="$1" sort="${2:-stars}" drop="${3:-}"
  gh api -X GET search/repositories -f q="$q" -f sort="$sort" -f order=desc -f per_page=25 \
    --jq '.items[] | "\(.stargazers_count)\t\(.pushed_at[:10])\t\(.full_name)\t\((.description // "")[:80])"' \
    | { [ -n "$drop" ] && grep -Ev "$drop" || cat; } \
    | column -t -s $'\t'
}

_d() { date -u -v-"$1"d +%Y-%m-%d 2>/dev/null || date -u -d "$1 days ago" +%Y-%m-%d; }

# Lane-agnostic. Young and already popular: the highest-signal filter on GitHub.
ghvelocity() { _gh_repo_search "stars:>${1:-500} created:>$(_d "${2:-60}") archived:false"; }

ghagents()     { _gh_repo_search "topic:claude-code stars:>100 pushed:>$(_d 60) archived:false"; }   # lane 1
ghmcp()        { _gh_repo_search "topic:mcp stars:>200 pushed:>$(_d 30) archived:false"; }           # lane 1
ghseo()        { _gh_repo_search "topic:seo topic:ai stars:>50 pushed:>$(_d 90) archived:false"; }   # lane 2
ghdigest()     { _gh_repo_search "\"research digest\" in:readme stars:>100 pushed:>$(_d 120) archived:false"; }  # lane 3
ghsanity()     { _gh_repo_search "topic:sanity topic:nextjs stars:>50 pushed:>$(_d 120) archived:false"; }       # lane 4
ghautomation() { _gh_repo_search "topic:automation topic:llm stars:>200 pushed:>$(_d 60) archived:false"; }      # lane 5
ghwriting()    { _gh_repo_search "\"fact check\" in:readme topic:llm stars:>100 pushed:>$(_d 120) archived:false"; }  # lane 6
ghgeo()        { _gh_repo_search "topic:geospatial stars:>300 pushed:>$(_d 90) archived:false"; }    # lane 7
ghnews()       { _gh_repo_search "topic:journalism stars:>100 pushed:>$(_d 300) archived:false"; }   # lane 8
ghdatajourn()  { _gh_repo_search "\"data journalism\" in:readme stars:>100 pushed:>$(_d 300) archived:false"; }  # lane 9
ghvideo()      { _gh_repo_search "topic:video-editing stars:>500 pushed:>$(_d 120) archived:false"; }            # lane 10

# Sweep one org. The good work in lanes 8 and 9 is concentrated, not diffuse.
ghorg() { _gh_repo_search "org:$1 pushed:>$(_d "${2:-365}")" updated; }

# Search READMEs by the words you would use out loud. The friction-list channel.
#
# Not an exact-phrase search. The original quoted "$1", which meant a README had
# to contain the sentence verbatim -- "merge place records", "government dataset
# cleaning" and "keep statistics in sync" all returned exactly zero repos, because
# nobody writes their README in your words. Unquoted, the terms are ANDed.
#
# The star ceiling and the NOT list are what make the unquoted version usable.
# Without them the results are just the biggest repos on GitHub that happen to
# contain the words anywhere: public-apis, awesome-selfhosted, yt-dlp. Same
# junk the scored pipeline hard-excludes in global_excludes; ghfriction had no
# filtering at all.
#
# Phrase it as concrete technical nouns, not as the problem in the abstract:
#   ghfriction "speaker diarization transcript"   -> WhisperLiveKit, FunClip
#   ghfriction "government data cleaning csv"     -> PUDL, practical-sql-2
# Second arg raises the star floor, third lowers the ceiling.
GHFRICTION_NOT="NOT awesome NOT curated NOT roadmap NOT cheatsheet NOT interview"

# The catch-all repos. A TIL log, a second-brain vault, a boilerplate collection or
# a language-basics course contains every word you can think of, so it matches any
# ANDed term set and outranks the real answer on stars alone. Observed on the
# 2026-09-06 friction-list run: jbranchaud/til came back first for three unrelated
# queries. These cannot go in GHFRICTION_NOT -- the five-operator ceiling is full --
# so they are dropped after the fact, the same way global_excludes works in radar.py.
GHFRICTION_DROP='[Tt]oday [Ii] [Ll]earned|/til$|[Ss]econd [Bb]rain|[Bb]oilerplate|[Bb]asics \( ?v[0-9]|[Ll]earning-zone/|[Ee]xamples? of|[Ss]tudy [Gg]uide|[Cc]ollection of (examples|patterns|snippets)'

ghfriction() {
  _gh_repo_search "$1 in:readme stars:${2:-50}..${3:-20000} pushed:>$(_d 180) archived:false $GHFRICTION_NOT" \
    stars "$GHFRICTION_DROP"
}
