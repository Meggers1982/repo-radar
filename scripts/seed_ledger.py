"""Seed the ledger from repos already starred, so the radar never surfaces
something already looked at.

Run once at setup, and again any time a batch of stars accumulates. Because
Gate 1 says to star everything screened, including rejects, the star list
doubles as the "already considered" set.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

LEDGER = Path(__file__).resolve().parent.parent / "ledger" / "seen.json"
STAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def starred(token: str):
    page, out = 1, []
    while True:
        req = Request(
            f"https://api.github.com/user/starred?per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": f"Bearer {token}",
                     "User-Agent": "repo-radar"},
        )
        with urlopen(req, timeout=30) as resp:
            batch = json.loads(resp.read())
        if not batch:
            return out
        out += batch
        page += 1


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("ERROR: set GITHUB_TOKEN (try: GITHUB_TOKEN=$(gh auth token))")

    seen = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    added = 0
    for repo in starred(token):
        record = seen.setdefault(repo["full_name"], {
            "first_seen": STAMP,
            "stars_at_first_seen": repo.get("stargazers_count", 0),
        })
        if not record.get("surfaced"):
            record["surfaced"] = "starred"
            added += 1

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n")
    print(f"seeded {added} starred repos · ledger holds {len(seen)}")


if __name__ == "__main__":
    main()
