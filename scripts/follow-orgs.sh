#!/usr/bin/env bash
# Follow the orgs and maintainers behind each live lane, so their new repos and
# their stars land in the GitHub feed. Section 4B of the strategy doc.
#
# Needs the "user:follow" scope, which the default gh token does not carry:
#   gh auth refresh -h github.com -s user:follow
# Then:
#   bash ~/repo-radar/scripts/follow-orgs.sh
#
# The list is READ FROM config/lanes.json rather than repeated here. It used to
# be a hand-maintained copy and drifted twice -- once when lane 9 gained three
# orgs, and again when lanes 3, 4, 6, 7 and 10 were cut on 2026-09-06 and their
# orgs (sanity-io, vercel, remotion-dev, openai, m-bain, Zulko) should have gone
# with them. Retired lanes live under "retired_lanes" and are skipped, so cutting
# a lane now removes its orgs here automatically.

set -u
cd "$(dirname "$0")/.." || exit 1

follow() {
  gh api -X PUT "user/following/$1" --silent 2>/dev/null \
    && echo "  ok   $1" || echo "  FAIL $1"
}

python3 - <<'PY' > /tmp/repo-radar-orgs.$$
import json
c = json.load(open("config/lanes.json"))
for lane in c["lanes"]:
    for org in lane.get("orgs", []):
        print(lane["id"], lane["name"], org, sep="\t")
PY

current_lane=""
seen=""
while IFS=$'\t' read -r lane_id lane_name org; do
  if [ "$lane_id" != "$current_lane" ]; then
    echo "Lane $lane_id — $lane_name"
    current_lane="$lane_id"
  fi
  # An org can sit in two lanes; follow it once.
  case " $seen " in *" $org "*) echo "  --   $org (already followed above)"; continue;; esac
  seen="$seen $org"
  follow "$org"
done < /tmp/repo-radar-orgs.$$
rm -f /tmp/repo-radar-orgs.$$

# user/following is paginated at 30, so 'length' silently under-counts once the
# list grows past a page. Page through and count logins instead.
echo
echo "following $(gh api user/following --paginate --jq '.[].login' | wc -l | tr -d ' ') accounts"
