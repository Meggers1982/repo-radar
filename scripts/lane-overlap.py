#!/usr/bin/env python3
"""Measure how separable the lanes are.

A lane is only doing work if the repos it claims are not already claimed by
another lane. When one lane's vocabulary matches everything, cross-lane overlap
stops carrying information and the crossover multipliers in lanes.json fire on
almost every pick -- boosting exactly the generic repos they were written to
suppress. MEA-239.

    python3 scripts/lane-overlap.py --cache /tmp/raw.json          # fetch + measure
    python3 scripts/lane-overlap.py --cache /tmp/raw.json --offline  # re-measure

--offline re-fits the cached repos against the CURRENT lanes.json without
spending a single request, which is what makes a before/after comparison of a
config change honest: same repos, different rules.
"""
import argparse, json, os, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from radar import expand_dates, search, lane_evidence, days_since  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "lanes.json"


def fetch_all(config, token):
    """Every lane query plus the velocity query, deduplicated by full_name."""
    found = {}
    queries = [(l, q) for l in config["lanes"] for q in l["queries"]]
    if config.get("velocity_query", {}).get("enabled"):
        queries.append((None, config["velocity_query"]["query"]))
    per_page = config["settings"]["results_per_query"]
    for lane, raw in queries:
        query = expand_dates(raw)
        sort = "updated" if (lane and "org:" in query) else "stars"
        items = search(query, per_page, token, sort)
        label = f"lane {lane['id']}" if lane else "velocity"
        print(f"  {label}: {len(items):>3} · {query}", file=sys.stderr)
        for repo in items:
            found.setdefault(repo["full_name"], repo)
        time.sleep(2.5)
    return list(found.values())


def measure(repos, config):
    """Per-lane claim counts and the pairwise overlap that matters."""
    lanes = config["lanes"]
    min_age = config["settings"].get("min_age_days", 0)
    claims, pair, strong_claims = Counter(), Counter(), Counter()
    fits = {}
    for repo in repos:
        if days_since(repo.get("created_at", "")) < min_age:
            continue
        hit = {}
        for lane in lanes:
            ev = lane_evidence(repo, lane)
            if ev:
                hit[lane["id"]] = ev
        if not hit:
            continue
        fits[repo["full_name"]] = hit
        for lid, ev in hit.items():
            claims[lid] += 1
            if ev == "strong":
                strong_claims[lid] += 1
        # Only strong evidence earns a crossover, so only strong pairs matter.
        strong = sorted(l for l, e in hit.items() if e == "strong")
        for a in range(len(strong)):
            for b in range(a + 1, len(strong)):
                pair[(strong[a], strong[b])] += 1
    return claims, strong_claims, pair, fits


def report(claims, strong_claims, pair, fits, config):
    lanes = config["lanes"]
    names = {l["id"]: l["name"] for l in lanes}
    total = len(fits)
    print(f"\n{total} repos fit at least one lane\n")
    print(f"{'lane':<5} {'claims':>7} {'strong':>7} {'share':>7}  name")
    for l in lanes:
        lid = l["id"]
        share = strong_claims[lid] / total if total else 0
        print(f"{lid:<5} {claims[lid]:>7} {strong_claims[lid]:>7} {share:>6.0%}  {names[lid]}")

    print("\nStrong-evidence overlap — of each lane's strongly-claimed repos,")
    print("the share also strongly claimed by another lane:\n")
    worst = []
    for l in lanes:
        a = l["id"]
        base = strong_claims[a]
        if not base:
            continue
        for other in lanes:
            b = other["id"]
            if a == b:
                continue
            n = pair[(min(a, b), max(a, b))]
            if n / base >= 0.5:
                worst.append((n / base, a, b, n, base))
    if not worst:
        print("  none above 50% — the lanes are separable.")
    for share, a, b, n, base in sorted(worst, reverse=True):
        print(f"  lane {a:>2} → lane {b:<2}  {share:>4.0%}  ({n}/{base})")

    crossovers = {k: v for k, v in config.get("crossovers", {}).items()
                  if not k.startswith("_")}
    if crossovers:
        st = config["settings"]
        generic = 1.0 + st.get("multi_lane_step", 0.35)
        print("\nCrossover multipliers. radar.py takes max(multi_lane, crossover), so a")
        print(f"value at or below the generic two-lane bonus ({generic:.2f}) never fires:\n")
        for key, mult in sorted(crossovers.items(), key=lambda kv: -kv[1]):
            a, b = (int(x) for x in key.split("+"))
            n = pair[(min(a, b), max(a, b))]
            flag = "" if mult > generic else "   INERT — never beats the generic bonus"
            print(f"  {key:<6} ×{mult:<5} matches {n:>3} repos ({n / total:>3.0%}){flag}")
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, help="raw search results JSON")
    ap.add_argument("--offline", action="store_true",
                    help="re-fit the cached repos against the current lanes.json")
    args = ap.parse_args()

    config = json.loads(CONFIG_PATH.read_text())
    cache = Path(args.cache)

    if args.offline:
        repos = json.loads(cache.read_text())
        print(f"re-fitting {len(repos)} cached repos against current lanes.json",
              file=sys.stderr)
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        if not token:
            print("WARNING: no GITHUB_TOKEN; search is rate limited to 10/min",
                  file=sys.stderr)
        repos = fetch_all(config, token)
        cache.write_text(json.dumps(repos))
        print(f"cached {len(repos)} repos to {cache}", file=sys.stderr)

    claims, strong_claims, pair, fits = measure(repos, config)
    worst = report(claims, strong_claims, pair, fits, config)
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
