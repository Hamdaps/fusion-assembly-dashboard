# Fusion Assembly Bug Reduction Dashboard

Live at **https://hamdaps.github.io/fusion-assembly-dashboard/**

Tracks the Aug 1, 2026 bug-reduction push for teams Ebony, Pearl, Synora and Riva
in the Jira `FUS` project. Target: a 20% cut in the open bug backlog
(295 → 236).

## How it works

```
.github/workflows/sync-jira.yml   hourly cron ─┐
scripts/fetch_jira.py             queries Jira ┴─> docs/data.json
docs/index.html                   fetches data.json at load and renders
```

`docs/index.html` holds **no numbers**. Every figure, chart and table row is
rendered client-side from `docs/data.json`, so a sync only ever rewrites that
one small file. An open tab re-polls `data.json` every 10 minutes.

## Setup (one time)

1. **Add repository secrets** — Settings → Secrets and variables → Actions:
   - `JIRA_USERNAME` — your Atlassian account email
   - `JIRA_API_TOKEN` — a *classic* token from
     [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
     Scoped tokens do not work with basic auth and will fail with 401.
2. **Confirm Pages** — Settings → Pages → Source: `main` branch, `/docs` folder.
3. **Test it** — Actions → *Sync Jira data* → Run workflow. Check the log for
   `wrote docs/data.json: … open, …% reduction`.

Run locally the same way:

```bash
export JIRA_USERNAME='you@autodesk.com'
export JIRA_API_TOKEN='...'
python3 scripts/fetch_jira.py
```

Stdlib only — no dependencies to install.

## Things that will bite you

**The Aug 1 baselines are hardcoded.** `BASELINE` and `BASELINE_TOTAL` in
`scripts/fetch_jira.py` are historical facts. Jira has no snapshot of what was
open on Aug 1, so these cannot be recomputed — do not "fix" them to match a
live query.

**Team membership spans two custom fields.** A bug belongs to a team via
`Development Team` *or* `ADSK Team`, and at least one bug carries a different
value in each. Every query ORs across both. This is why the per-team baselines
sum to 296 while the combined baseline is 295: that bug is counted once
combined, twice per-team.

**"Incoming since Aug 1" can go down.** It is `created >= 2026-08-01`, which
should only grow, but a bug whose team field is reassigned away from the four
teams silently leaves the filter. Between Sep 8 and Sep 9 the count fell 41 → 38
this way. A drop means scope churn, not a data bug.

**The baseline cohort drifts.** Re-deriving "open as of Aug 1" today
(`created < Aug 1 AND (unresolved OR resolved after Aug 1)`) yields 293–294, not
295, for the same reason. This is why `baseline + incoming − resolved` misses
current open by 1–2.

## Related

- Confluence page (narrative + history):
  https://autodesk.atlassian.net/wiki/spaces/F360/pages/1109491897
- `create-fab-jira-dashboard.sh` (in `~/Git-projects`) builds an equivalent
  native Jira dashboard.
