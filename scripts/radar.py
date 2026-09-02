"""repo-radar: standing GitHub queries for the ten-lane interest map.

Runs the queries in config/lanes.json, scores what comes back, drops anything
already surfaced, and writes a ranked report grouped by lane.

No LLM calls anywhere in this pipeline. Everything here is the GitHub search
API plus deterministic scoring, so it runs on the GITHUB_TOKEN that Actions
provides for free and cannot be blocked by an API balance.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "lanes.json"
LEDGER_PATH = REPO_ROOT / "ledger" / "seen.json"
OUTPUTS_DIR = REPO_ROOT / "outputs"
DASHBOARD_DIR = REPO_ROOT / "docs" / "data"

API = "https://api.github.com/search/repositories"
DATE_MACRO = re.compile(r"\{d-(\d+)\}")
NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------- utilities

def expand_dates(query: str) -> str:
    """Replace {d-N} with the ISO date N days ago, so queries never go stale."""
    return DATE_MACRO.sub(
        lambda m: (NOW - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d"), query
    )


def days_since(iso: str) -> float:
    if not iso:
        return 9999.0
    stamp = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max((NOW - stamp).total_seconds() / 86400.0, 0.0)


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


# ------------------------------------------------------------ github search

def search(query: str, per_page: int, token: str, sort: str = "stars"):
    url = f"{API}?{urlencode({'q': query, 'sort': sort, 'order': 'desc', 'per_page': per_page})}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "repo-radar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(4):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as resp:
                return json.loads(resp.read()).get("items", [])
        except HTTPError as err:
            # 403/429 here is the search rate limit (30/min authenticated), not a
            # permissions problem. Back off and retry rather than losing the lane.
            if err.code in (403, 429) and attempt < 3:
                wait = 20 * (attempt + 1)
                print(f"    rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    query failed ({err.code}): {query}", file=sys.stderr)
            return []
        except Exception as err:
            print(f"    query error: {err}", file=sys.stderr)
            return []
    return []


# -------------------------------------------------------------- lane fitting

def lane_evidence(repo: dict, lane: dict) -> str:
    """How strongly a repo belongs to a lane.

    "strong" means the maintainer's own topic tag or the owner org says so.
    "weak" means only a keyword appeared in the name or description, which is
    noisy: several lanes legitimately share vocabulary ("transcription" belongs
    to both journalism and video), and treating those matches as equal produced
    fake crossovers on the first tuning run. Only strong evidence earns a
    crossover multiplier.
    """
    topics = {t.lower() for t in repo.get("topics") or []}
    if topics & {t.lower() for t in lane.get("topics", [])}:
        return "strong"

    owner = (repo.get("owner") or {}).get("login", "").lower()
    if owner in {o.lower() for o in lane.get("orgs", [])}:
        return "strong"

    text = f"{repo.get('name', '')} {repo.get('description') or ''}".lower()
    if any(kw.lower() in text for kw in lane.get("keywords", [])):
        return "weak"
    return ""


def excluded(repo: dict, pattern: str) -> bool:
    if not pattern:
        return False
    text = f"{repo.get('name', '')} {repo.get('description') or ''}"
    return bool(re.search(pattern, text))


# ------------------------------------------------------------------ scoring

def score_repo(repo: dict, lanes_hit: list, config: dict, seen: dict) -> dict:
    stars = repo.get("stargazers_count", 0)
    age = max(days_since(repo.get("created_at", "")), 1.0)
    stale = days_since(repo.get("pushed_at", ""))

    # Monthly star velocity, log-damped. Age-relative popularity, not raw popularity.
    velocity = math.log10(1 + (stars / age) * 30)
    velocity = min(velocity, config["settings"].get("velocity_cap", 4.0))

    # Star deflation and the freshness floor come from the LEAD lane, not from
    # max() across every matched lane. Using max() cancelled lane 10's deliberate
    # star deflation for any repo that also touched lane 1, which is most of them.
    lead = lanes_hit[0]
    star_weight = lead.get("star_weight", 1.0)
    floor = lead.get("freshness_floor", 0.15)
    lane_weight = max(l.get("weight", 1.0) for l in lanes_hit)

    freshness = max(1.0 - (stale / 365.0), floor)
    strong = [l for l in lanes_hit if l.get("_evidence") == "strong"]
    multi_lane = 1.0 + 0.5 * max(len(strong) - 1, 0)

    crossover = 1.0
    ids = sorted(l["id"] for l in lanes_hit if l.get("_evidence") == "strong")
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            crossover = max(crossover, config["crossovers"].get(f"{ids[a]}+{ids[b]}", 1.0))

    owner = (repo.get("owner") or {}).get("login", "").lower()
    followed = any(owner in {o.lower() for o in l.get("orgs", [])} for l in lanes_hit)
    org_bonus = 1.25 if followed else 1.0

    # Growth since a previous run saw it but did not surface it.
    record = seen.get(repo["full_name"], {})
    gained = stars - record.get("stars_at_first_seen", stars)
    growth = math.log10(1 + max(gained, 0)) * 0.4

    score = velocity * star_weight * freshness * lane_weight * multi_lane * crossover * org_bonus + growth

    return {
        "full_name": repo["full_name"],
        "url": repo["html_url"],
        "description": (repo.get("description") or "").strip(),
        "stars": stars,
        "stars_gained": gained if record else None,
        "language": repo.get("language"),
        "topics": (repo.get("topics") or [])[:8],
        "created": repo.get("created_at", "")[:10],
        "pushed": repo.get("pushed_at", "")[:10],
        "days_since_push": round(stale),
        "license": ((repo.get("license") or {}).get("spdx_id") or "none"),
        "lanes": [{"id": l["id"], "name": l["name"]} for l in lanes_hit],
        "weak_lanes": all(l.get("_evidence") != "strong" for l in lanes_hit),
        "crossover": round(crossover, 2),
        "followed_org": followed,
        "score": round(score, 3),
    }


# ------------------------------------------------------------------- report

def lane_is_due(lane: dict, cadence: str) -> bool:
    if cadence == "all":
        return True
    if cadence == "weekly":
        return lane.get("cadence") == "weekly"
    return True  # monthly runs everything


def build_report(picks: list, cadence: str, lane_names: dict) -> str:
    stamp = NOW.strftime("%Y-%m-%d")
    lines = [
        f"# repo-radar — {stamp}",
        "",
        f"**Run:** {cadence} | **Candidates:** {len(picks)}",
        "",
        "Screen these at Gate 1: does it sit in one lane or two, last commit inside 90 days "
        "(lane 9 exempt), a license, a README that shows output, a named maintainer, issues that "
        "get answered, no paywall before evaluation. Two failures and close the tab. Star everything "
        "you screen either way.",
        "",
    ]

    by_lane = {}
    for pick in picks:
        by_lane.setdefault(pick["lanes"][0]["id"], []).append(pick)

    for lane_id in sorted(by_lane):
        lines.append(f"## Lane {lane_id}: {lane_names[lane_id]}")
        lines.append("")
        for pick in by_lane[lane_id]:
            flags = []
            if len(pick["lanes"]) > 1:
                others = ", ".join(str(l["id"]) for l in pick["lanes"][1:])
                flags.append(f"also lanes {others}")
            if pick.get("weak_lanes"):
                flags.append("weak match")
            if pick["crossover"] > 1.0:
                flags.append("**crossover**")
            if pick["followed_org"]:
                flags.append("followed org")
            if pick["stars_gained"]:
                flags.append(f"+{pick['stars_gained']} stars since first seen")
            suffix = f" — _{'; '.join(flags)}_" if flags else ""

            lines.append(f"### [{pick['full_name']}]({pick['url']}) · {pick['score']}{suffix}")
            lines.append("")
            lines.append(pick["description"] or "_No description._")
            lines.append("")
            lines.append(
                f"`{pick['stars']:,}` stars · created {pick['created']} · "
                f"pushed {pick['pushed']} ({pick['days_since_push']}d ago) · "
                f"{pick['language'] or 'n/a'} · {pick['license']}"
            )
            lines.append("")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Run the repo-radar lane queries.")
    parser.add_argument("--cadence", choices=["weekly", "monthly", "all"], default="weekly",
                        help="weekly runs the fast lanes (1, 2, 5); monthly runs everything")
    parser.add_argument("--lane", type=int, action="append",
                        help="run only this lane id (repeatable)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the report without writing outputs or the ledger")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text())
    settings = config["settings"]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        print("WARNING: no GITHUB_TOKEN set. Unauthenticated search allows only 10 "
              "requests/minute and will rate limit.", file=sys.stderr)

    lanes = config["lanes"]
    if args.lane:
        active = [l for l in lanes if l["id"] in args.lane]
    else:
        active = [l for l in lanes if lane_is_due(l, args.cadence)]

    seen = load_json(LEDGER_PATH, {})
    global_exclude = config.get("global_excludes", {}).get("name_or_description", "")

    print(f"repo-radar · {args.cadence} run · lanes {[l['id'] for l in active]}", file=sys.stderr)

    # Collect raw results, remembering which lane's query found each repo.
    found, provenance = {}, {}
    queries = [(l, q) for l in active for q in l["queries"]]
    if config.get("velocity_query", {}).get("enabled") and not args.lane:
        queries.append((None, config["velocity_query"]["query"]))

    for lane, raw in queries:
        query = expand_dates(raw)
        label = f"lane {lane['id']}" if lane else "velocity"
        sort = "stars" if not lane else ("updated" if "org:" in query else "stars")
        items = search(query, settings["results_per_query"], token, sort)
        print(f"  {label}: {len(items):>3} · {query}", file=sys.stderr)
        for repo in items:
            found.setdefault(repo["full_name"], repo)
            if lane and repo["full_name"] not in provenance:
                provenance[repo["full_name"]] = lane["id"]
        time.sleep(2.5)  # search API allows 30/min authenticated

    # Score everything, applying lane fit and hard excludes.
    scored = []
    min_age = settings.get("min_age_days", 0)
    for repo in found.values():
        if excluded(repo, global_exclude):
            continue
        if days_since(repo.get("created_at", "")) < min_age:
            continue

        hits = []
        for lane in lanes:
            evidence = lane_evidence(repo, lane)
            if evidence:
                hits.append(dict(lane, _evidence=evidence))
        if not hits:
            continue
        if any(excluded(repo, l.get("excludes", {}).get("name_or_description", "")) for l in hits):
            continue

        # A repo leads under the lane whose query found it. Falling back to lane
        # weight put an AIGC video engine at the top of the automation lane on
        # the first run, because that lane happened to carry a higher weight.
        source = provenance.get(repo["full_name"])
        hits.sort(key=lambda l: (
            l["id"] == source,
            l.get("_evidence") == "strong",
            l.get("weight", 1.0),
        ), reverse=True)
        scored.append(score_repo(repo, hits, config, seen))

    scored.sort(key=lambda r: r["score"], reverse=True)

    # Drop anything already surfaced. A repo appears once, ever.
    fresh = [r for r in scored if not seen.get(r["full_name"], {}).get("surfaced")]
    fresh = [r for r in fresh if r["score"] >= settings["min_score"]]

    picks, per_lane = [], {}
    guaranteed = settings.get("guaranteed_per_lane", 2)

    def take(repo):
        lead = repo["lanes"][0]["id"]
        picks.append(repo)
        per_lane[lead] = per_lane.get(lead, 0) + 1

    # First pass: every lane that returned anything gets its top few, so a loud
    # lane cannot crowd out a quiet one.
    for repo in fresh:
        if per_lane.get(repo["lanes"][0]["id"], 0) < guaranteed:
            take(repo)

    # Second pass: fill the remaining slots by score alone.
    taken = {r["full_name"] for r in picks}
    for repo in fresh:
        if len(picks) >= settings["max_candidates_total"]:
            break
        if repo["full_name"] in taken:
            continue
        if per_lane.get(repo["lanes"][0]["id"], 0) >= settings["max_candidates_per_lane"]:
            continue
        take(repo)

    picks.sort(key=lambda r: r["score"], reverse=True)
    picks = picks[:settings["max_candidates_total"]]

    lane_names = {l["id"]: l["name"] for l in lanes}
    report = build_report(picks, args.cadence, lane_names)

    if args.dry_run:
        print(report)
        print(f"\n[dry run] {len(found)} found · {len(scored)} in-lane · "
              f"{len(fresh)} new · {len(picks)} surfaced", file=sys.stderr)
        return

    # Ledger: remember everything scored, mark only what surfaced.
    stamp = NOW.strftime("%Y-%m-%d")
    for repo in scored:
        record = seen.setdefault(repo["full_name"], {
            "first_seen": stamp,
            "stars_at_first_seen": repo["stars"],
        })
        record["last_seen"] = stamp
        record["stars_last_seen"] = repo["stars"]
    for repo in picks:
        seen[repo["full_name"]]["surfaced"] = stamp

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / f"repo-radar-{stamp}-{args.cadence}.md").write_text(report)

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    runs = load_json(DASHBOARD_DIR / "index.json", {"runs": []})
    runs["runs"] = [r for r in runs["runs"] if r["id"] != f"{stamp}-{args.cadence}"]
    runs["runs"].insert(0, {
        "id": f"{stamp}-{args.cadence}",
        "date": stamp,
        "cadence": args.cadence,
        "count": len(picks),
        "picks": picks,
    })
    runs["runs"] = runs["runs"][:52]
    runs["lanes"] = [{"id": l["id"], "name": l["name"]} for l in lanes]
    runs["updated"] = stamp
    (DASHBOARD_DIR / "index.json").write_text(json.dumps(runs, indent=2) + "\n")

    print(f"\n{len(found)} found · {len(scored)} in-lane · {len(fresh)} new · "
          f"{len(picks)} surfaced · ledger holds {len(seen)}", file=sys.stderr)
    print(report)


if __name__ == "__main__":
    main()
