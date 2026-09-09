#!/usr/bin/env python3
"""Query Jira and regenerate docs/data.json for the Fusion Assembly dashboard.

Stdlib only -- no pip install needed in CI.

Env:
  JIRA_USERNAME   Atlassian account email
  JIRA_API_TOKEN  classic API token (id.atlassian.com/manage-profile/security/api-tokens)
  JIRA_SITE       optional, defaults to https://autodesk.atlassian.net
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = os.environ.get("JIRA_SITE", "https://autodesk.atlassian.net").rstrip("/")
USER = os.environ.get("JIRA_USERNAME")
TOKEN = os.environ.get("JIRA_API_TOKEN")

BASELINE_DATE = "2026-08-01"

# Open-bug counts snapshotted on the baseline date. Historical facts: Jira cannot
# recompute these, so they are pinned here and must not be derived at runtime.
BASELINE = {"Ebony": 215, "Pearl": 74, "Synora": 4, "Riva": 3}
BASELINE_TOTAL = 295  # combined query; 1 lower than sum(BASELINE) -- see README

TEAMS = ["Ebony", "Pearl", "Synora", "Riva"]
TEAM_CLAUSE = (
    '("Development Team" in (Ebony, Pearl, Synora, Riva) '
    'OR "ADSK Team" in (Ebony, Pearl, Synora, Riva))'
)
PRIORITY_ORDER = ["1. Blocker", "2. Critical", "3. Major", "4. Minor", "6. None"]
# Resolutions that mean a code/data change actually shipped.
FIX_RESOLUTIONS = {"Fixed", "Data Fixed", "Incidentally Fixed", "Done"}

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data.json"


def _auth_header() -> str:
    if not USER or not TOKEN:
        sys.exit("JIRA_USERNAME and JIRA_API_TOKEN must both be set")
    raw = f"{USER}:{TOKEN}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        SITE + path,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": _auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        sys.exit(f"Jira API {e.code} on {path}\n{body}")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach {SITE}: {e.reason}")


def search(jql: str, fields: list[str] | None = None) -> list[dict]:
    """Page through every match. Exact counts, no approximate-count endpoint."""
    out: list[dict] = []
    token = None
    while True:
        payload = {"jql": jql, "maxResults": 100, "fields": fields or ["key"]}
        if token:
            payload["nextPageToken"] = token
        data = _post("/rest/api/3/search/jql", payload)
        out.extend(data.get("issues", []))
        token = data.get("nextPageToken")
        if data.get("isLast", True) or not token:
            break
        if len(out) > 5000:  # runaway guard
            break
    return out


def base_for(team: str | None) -> str:
    if team is None:
        return f"project = FUS AND issuetype = Bug AND {TEAM_CLAUSE}"
    return (
        f'project = FUS AND issuetype = Bug AND '
        f'("Development Team" = {team} OR "ADSK Team" = {team})'
    )


def counts_for(team: str | None) -> dict:
    b = base_for(team)
    return {
        "open": len(search(f"{b} AND resolution IS EMPTY")),
        "incoming": len(search(f'{b} AND created >= "{BASELINE_DATE}"')),
        "resolved": len(search(f'{b} AND resolutiondate >= "{BASELINE_DATE}"')),
    }


def tone_for(pct: float, to_go: int) -> str:
    if to_go <= 0:
        return "green"
    return "yellow" if pct >= 10 else "red"


def build_team(name: str, c: dict) -> dict:
    baseline = BASELINE[name]
    target = round(baseline * 0.8)
    to_go = c["open"] - target
    pct = round((baseline - c["open"]) / baseline * 100, 1)
    return {
        "name": name,
        "baseline": baseline,
        "target": target,
        "open": c["open"],
        "incoming": c["incoming"],
        "resolved": c["resolved"],
        "pct": pct,
        "to_go": to_go,
        "status": "Target met" if to_go <= 0 else f"{to_go} to go",
        "tone": tone_for(pct, to_go),
    }


def tally(values: list[str], order: list[str] | None = None) -> list[dict]:
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    if order:
        keys = [k for k in order if k in counts] + sorted(k for k in counts if k not in order)
    else:
        keys = sorted(counts, key=lambda k: (-counts[k], k))
    return [{"label": k, "count": counts[k]} for k in keys]


def main() -> None:
    combined = counts_for(None)

    resolved_issues = search(
        f'{base_for(None)} AND resolutiondate >= "{BASELINE_DATE}"',
        fields=["priority", "resolution"],
    )

    def field_name(issue: dict, key: str) -> str:
        node = (issue.get("fields") or {}).get(key) or {}
        return node.get("name") or "(none)"

    resolutions = [field_name(i, "resolution") for i in resolved_issues]
    priorities = [field_name(i, "priority") for i in resolved_issues]
    fixed_count = sum(1 for r in resolutions if r in FIX_RESOLUTIONS)

    target_total = round(BASELINE_TOTAL * 0.8)
    to_go_total = combined["open"] - target_total
    pct_total = round((BASELINE_TOTAL - combined["open"]) / BASELINE_TOTAL * 100, 1)

    teams = [build_team(t, counts_for(t)) for t in TEAMS]

    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_date": BASELINE_DATE,
        "site": SITE,
        "confluence_url": (
            "https://autodesk.atlassian.net/wiki/spaces/F360/pages/1109491897"
        ),
        "totals": {
            "baseline": BASELINE_TOTAL,
            "target": target_total,
            "open": combined["open"],
            "incoming": combined["incoming"],
            "resolved": combined["resolved"],
            "pct": pct_total,
            "to_go": to_go_total,
            "tone": tone_for(pct_total, to_go_total),
        },
        "teams": teams,
        "resolved_total": len(resolved_issues),
        "resolved_fixed": fixed_count,
        "resolved_disposition": len(resolved_issues) - fixed_count,
        "resolved_by_resolution": tally(resolutions),
        "resolved_by_priority": tally(priorities, PRIORITY_ORDER),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    t = data["totals"]
    print(
        f"wrote {OUT.relative_to(ROOT)}: {t['open']} open, "
        f"{t['pct']}% reduction, {t['to_go']} to go, "
        f"{data['resolved_total']} resolved"
    )


if __name__ == "__main__":
    main()
