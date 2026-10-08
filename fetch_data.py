#!/usr/bin/env python3
"""Fetch a user's all-time daily contribution calendar via the GitHub CLI into data/contributions.json.

Usage: fetch_data.py [login]   (default: h3h; requires an authenticated `gh`)
"""
import json, subprocess, sys, datetime as dt
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "h3h"
OUT = Path(__file__).parent / "data" / "contributions.json"

def gql(query):
    return json.loads(subprocess.check_output(["gh", "api", "graphql", "-f", f"query={query}"]))["data"]

years = gql(f'{{user(login:"{LOGIN}"){{contributionsCollection{{contributionYears}}}}}}')
years = sorted(years["user"]["contributionsCollection"]["contributionYears"])

days, private_by_year = [], {}
for y in years:
    c = gql(f'{{user(login:"{LOGIN}"){{contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z")'
            f'{{restrictedContributionsCount contributionCalendar{{weeks{{contributionDays{{date contributionCount}}}}}}}}}}}}')
    c = c["user"]["contributionsCollection"]
    private_by_year[str(y)] = c["restrictedContributionsCount"]
    for w in c["contributionCalendar"]["weeks"]:
        for d in w["contributionDays"]:
            if d["date"].startswith(str(y)):
                days.append([d["date"], d["contributionCount"]])
    print(y, sum(n for d, n in days if d.startswith(str(y))), file=sys.stderr)

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps({"login": LOGIN, "as_of": dt.date.today().isoformat(),
                           "private_by_year": private_by_year, "days": days}, separators=(",", ":")) + "\n")
print(f"wrote {OUT} ({len(days)} days)")
