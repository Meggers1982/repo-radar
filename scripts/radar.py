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
CONTENTS_API = "https://api.github.com/repos/{}/contents"
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


def api_get(url: str, token: str):
    """One plain REST GET. Returns None on any failure; callers treat that as
    "no information", never as a reason to keep or drop a repo by accident."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "repo-radar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ------------------------------------------------------------ language gate

# A script test, not a language test. It answers the only question the radar
# needs answered — can this listing be screened at Gate 1 as written — without
# an LLM and without a language-detection dependency. Spanish, German and
# Indonesian repos pass, which is correct: they are readable, and Gate 1 is a
# skim, not a translation exercise.
LATIN_LETTER = re.compile(r"[A-Za-z]")
NON_LATIN = re.compile(
    "[\u0400-\u052f"              # Cyrillic
    "\u0590-\u05ff\u0600-\u06ff\u0700-\u074f"   # Hebrew, Arabic, Syriac
    "\u0900-\u0dff\u0e00-\u0e7f"                  # Indic scripts, Thai
    "\u1100-\u11ff\u3040-\u30ff\u3130-\u318f"   # Jamo, kana
    "\u3400-\u4dbf\u4e00-\u9fff"                  # CJK ideographs
    "\ua960-\ua97f\uac00-\ud7af"                  # Hangul
    "\uf900-\ufaff\uff00-\uff9f]"                 # CJK compat, fullwidth
)
# A repo that ships one of these has already done the translation itself.
README_EN = re.compile(
    r"^readme[._-]?(en|eng|english|en[_-](us|gb))\.(md|rst|txt|adoc)$", re.I
)


def english_share(text: str) -> float:
    """Share of the letters in text written in the Latin alphabet."""
    latin = len(LATIN_LETTER.findall(text))
    other = len(NON_LATIN.findall(text))
    if latin + other == 0:
        return 1.0  # digits, punctuation or emoji only: nothing to judge
    return latin / (latin + other)


def reads_as_english(repo: dict, threshold: float) -> bool:
    """Whether the repo's own description reads as English.

    The description is what the report prints and what Gate 1 is skimmed from,
    so it is what gets judged. Name and topics only stand in when there is no
    description at all — judging on them too let a repo with a wholly CJK
    description through on the strength of English topic tags, which is exactly
    the case the gate exists to catch. Bilingual descriptions, the common
    "English tagline, native README" shape, still clear the threshold.
    """
    text = (repo.get("description") or "").strip()
    if not text:
        text = " ".join([repo.get("name") or "", " ".join(repo.get("topics") or [])])
    return english_share(text) >= threshold


def english_readme(full_name: str, token: str) -> str:
    """Name of an English README variant in the repo root, or "".

    Only the root is listed. A translation parked in docs/ or .github/ costs a
    second request per repo and is rare enough not to pay for.
    """
    entries = api_get(CONTENTS_API.format(full_name), token)
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        name = entry.get("name", "")
        if entry.get("type") == "file" and README_EN.match(name):
            return name
    return ""


def filter_english(candidates: list, token: str, settings: dict):
    """Split candidates into readable ones and ones dropped for language.

    Non-English candidates are only checked for a translation while there is
    budget for it: the contents API is cheap (5,000/hour) but not free, and a
    run that surfaces two dozen repos should not spend a hundred requests
    checking the tail it will never print.
    """
    limit = settings.get("english_check_limit", 25)
    kept, dropped, checks = [], [], 0
    for repo in candidates:
        if repo.get("english", True):
            kept.append(repo)
            continue
        if checks >= limit:
            dropped.append(repo["full_name"])
            continue
        checks += 1
        found = english_readme(repo["full_name"], token)
        if found:
            repo["english_readme"] = found
            kept.append(repo)
        else:
            dropped.append(repo["full_name"])
    return kept, dropped


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
    settings = config["settings"]
    stars = repo.get("stargazers_count", 0)
    age = max(days_since(repo.get("created_at", "")), 1.0)
    stale = days_since(repo.get("pushed_at", ""))

    # Monthly star velocity, log-damped. Age-relative popularity, not raw popularity.
    velocity = math.log10(1 + (stars / age) * 30)
    velocity = min(velocity, settings.get("velocity_cap", 4.0))

    # Star deflation and the freshness floor come from the LEAD lane, not from
    # max() across every matched lane. Using max() cancelled lane 10's deliberate
    # star deflation for any repo that also touched lane 1, which is most of them.
    lead = lanes_hit[0]
    star_weight = lead.get("star_weight", 1.0)
    floor = lead.get("freshness_floor", 0.15)
    lane_weight = max(l.get("weight", 1.0) for l in lanes_hit)

    freshness = max(1.0 - (stale / 365.0), floor)

    # Multi-lane bonus. Capped, because the increment was uncapped and a repo
    # that tags itself into five lanes collected 3.0x for doing nothing but
    # spamming topics.
    strong = [l for l in lanes_hit if l.get("_evidence") == "strong"]
    extra = min(max(len(strong) - 1, 0), settings.get("multi_lane_cap", 2))
    multi_lane = 1.0 + settings.get("multi_lane_step", 0.35) * extra

    crossover = 1.0
    ids = sorted(l["id"] for l in lanes_hit if l.get("_evidence") == "strong")
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            crossover = max(crossover, config["crossovers"].get(f"{ids[a]}+{ids[b]}", 1.0))

    # Take the better of the two, never the product. Both terms are paid for the
    # SAME observation -- that the repo sits in more than one lane -- so
    # multiplying them counted it twice and compounded: a 1+9 pair earned
    # 1.5 x 1.6 = 2.4x, and a four-lane repo 4.0x. Nothing else in the formula
    # moves that far (lane weight spans 1.0-1.3, star_weight 0.6-1.0), so the
    # bonus decided the ranking on its own. Measured on the 2026-09-06 pool:
    # all 24 top-scoring repos were multi-lane and the best single-lane
    # specialist -- simonw/llm, from a followed org -- ranked #31.
    # A crossover is now the bonus for that specific pair rather than a
    # surcharge on top of the generic one, so an entry at or below the generic
    # two-lane value never fires. scripts/lane-overlap.py reports which.
    lane_bonus = max(multi_lane, crossover)

    owner = (repo.get("owner") or {}).get("login", "").lower()
    followed = any(owner in {o.lower() for o in l.get("orgs", [])} for l in lanes_hit)
    org_bonus = 1.25 if followed else 1.0

    # Growth since a previous run saw it but did not surface it.
    record = seen.get(repo["full_name"], {})
    gained = stars - record.get("stars_at_first_seen", stars)
    growth = math.log10(1 + max(gained, 0)) * 0.4

    score = velocity * star_weight * freshness * lane_weight * lane_bonus * org_bonus + growth

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
        "lane_bonus": round(lane_bonus, 2),
        "followed_org": followed,
        "english": True,          # set by the language gate in main()
        "english_readme": None,   # the translation that let a non-English repo through
        "score": round(score, 3),
    }


# ------------------------------------------------------------------- report

def lane_is_due(lane: dict, cadence: str) -> bool:
    if cadence == "all":
        return True
    if cadence == "weekly":
        return lane.get("cadence") == "weekly"
    return True  # monthly runs everything


def build_report(picks: list, cadence: str, lane_names: dict, dropped_lang=()) -> str:
    stamp = NOW.strftime("%Y-%m-%d")
    lines = [
        f"# repo-radar — {stamp}",
        "",
        f"**Run:** {cadence} | **Candidates:** {len(picks)}",
        "",
    ]
    if dropped_lang:
        lines += [
            f"**Dropped for language:** {len(dropped_lang)} "
            f"({', '.join(sorted(dropped_lang)[:6])}"
            f"{', …' if len(dropped_lang) > 6 else ''}) — not in English and no "
            "English README in the repo root.",
            "",
        ]
    lines += [
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
            gained = pick["stars_gained"]
            if gained:
                # Signed explicitly: an f-string "+{gained}" printed "+-1" for a
                # repo that had lost stars since the run that first saw it.
                flags.append(f"{gained:+,} stars since first seen")
            if pick.get("english_readme"):
                flags.append(f"translated: {pick['english_readme']}")
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
        entry = score_repo(repo, hits, config, seen)
        entry["english"] = reads_as_english(repo, settings.get("english_min_share", 0.6))
        scored.append(entry)

    scored.sort(key=lambda r: r["score"], reverse=True)

    # Drop anything already surfaced. A repo appears once, ever.
    fresh = [r for r in scored if not seen.get(r["full_name"], {}).get("surfaced")]
    # Weak-only matches clear a higher bar. Strong evidence is a topic tag the
    # maintainer chose or a followed org; weak is a lane keyword landing in the
    # name or description, and the lanes share vocabulary on purpose. At the
    # plain min_score a solo lane 9 run spent both of its guaranteed slots on an
    # OSINT reading guide and an OSINT community mirror, neither of which is a
    # tool.
    weak_min = settings.get("weak_min_score", settings["min_score"])
    fresh = [
        r for r in fresh
        if r["score"] >= (weak_min if r.get("weak_lanes") else settings["min_score"])
    ]

    # Language gate. A repo the report cannot be skimmed in is not a candidate,
    # unless the repo itself ships the translation. Runs last so it only spends
    # requests on repos that would otherwise have surfaced.
    dropped_lang = []
    if settings.get("require_english", True):
        fresh, dropped_lang = filter_english(fresh, token, settings)
        if dropped_lang:
            print(f"  language gate: dropped {len(dropped_lang)}", file=sys.stderr)

    picks, per_lane = [], {}
    guaranteed = settings.get("guaranteed_per_lane", 2)

    def take(repo):
        lead = repo["lanes"][0]["id"]
        picks.append(repo)
        per_lane[lead] = per_lane.get(lead, 0) + 1

    # First pass: every lane that returned anything gets its top few, so a loud
    # lane cannot crowd out a quiet one.
    #
    # Weak-only matches are not eligible here. "Weak" means no topic tag and no
    # followed org, just a lane keyword somewhere in the name or description,
    # and lanes share vocabulary. A guaranteed slot is meant to stay empty
    # rather than be filled with noise, which is the same reason min_score was
    # raised from 0.25. Weak matches can still earn a slot in the second pass
    # on score alone.
    for repo in fresh:
        if repo.get("weak_lanes"):
            continue
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
    report = build_report(picks, args.cadence, lane_names, dropped_lang)

    if args.dry_run:
        print(report)
        print(f"\n[dry run] {len(found)} found · {len(scored)} in-lane · "
              f"{len(fresh)} new · {len(dropped_lang)} not in English · "
              f"{len(picks)} surfaced", file=sys.stderr)
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
        "stats": {
            "found": len(found),
            "in_lane": len(scored),
            "new": len(fresh),
            "dropped_non_english": len(dropped_lang),
        },
        "picks": picks,
    })
    runs["runs"] = runs["runs"][:52]
    runs["lanes"] = [{"id": l["id"], "name": l["name"]} for l in lanes]
    runs["updated"] = stamp
    (DASHBOARD_DIR / "index.json").write_text(json.dumps(runs, indent=2) + "\n")

    print(f"\n{len(found)} found · {len(scored)} in-lane · {len(fresh)} new · "
          f"{len(dropped_lang)} not in English · {len(picks)} surfaced · "
          f"ledger holds {len(seen)}", file=sys.stderr)
    print(report)


if __name__ == "__main__":
    main()
