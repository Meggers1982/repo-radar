#!/usr/bin/env bash
# repo-radar lane queries for interactive use.
# Add to ~/.zshrc:   source ~/repo-radar/scripts/lane-queries.sh

_gh_repo_search() {
  local q="$1" sort="${2:-stars}"
  gh api -X GET search/repositories -f q="$q" -f sort="$sort" -f order=desc -f per_page=25 \
    --jq '.items[] | "\(.stargazers_count)\t\(.pushed_at[:10])\t\(.full_name)\t\((.description // "")[:80])"' \
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
ghfriction() {
  _gh_repo_search "$1 in:readme stars:${2:-50}..${3:-20000} pushed:>$(_d 180) archived:false $GHFRICTION_NOT"
}
