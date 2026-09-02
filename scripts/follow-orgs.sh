#!/usr/bin/env bash
# Follow the orgs and maintainers behind each lane, so their new repos and their
# stars land in the GitHub feed. Section 4B of the strategy doc.
#
# Needs the "user" scope, which the default gh token does not carry:
#   gh auth refresh -h github.com -s user
# Then:
#   bash ~/repo-radar/scripts/follow-orgs.sh

set -u
follow() { gh api -X PUT "user/following/$1" --silent 2>/dev/null && echo "  ok   $1" || echo "  FAIL $1"; }

echo "Lane 1 — agents";            for u in anthropics browser-use NVIDIA modal-labs; do follow "$u"; done
echo "Lanes 2,3 — content, research"; for u in firecrawl; do follow "$u"; done
echo "Lane 4 — web";               for u in vercel sanity-io; do follow "$u"; done
echo "Lane 8 — journalism";        for u in propublica themarshallproject MuckRock freedomofpress palewire; do follow "$u"; done
echo "Lane 9 — data journalism";   for u in simonw datadesk alephdata opensanctions wireservice jsvine observablehq infoculture OpenRefine; do follow "$u"; done
echo "Lane 10 — video";            for u in remotion-dev openai Zulko; do follow "$u"; done

echo; echo "following $(gh api user/following --jq 'length') accounts"
