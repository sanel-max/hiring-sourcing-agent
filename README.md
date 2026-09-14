# Sourcing Search

Slack `/search` in **#sourcing-search** -> pick a role from a modal -> sources
candidates from LinkedIn, X/Twitter, and Instagram via Apify, scores each one
against that role's criteria with Claude, and posts a ranked shortlist back
into the channel. Runs as a small always-on server (FastAPI), separate from
the sibling UGC creator-sourcing project.

## Pieces

- **[dashboard.html](dashboard.html)** — published as the "Sourcing Criteria"
  artifact. Your team maintains role criteria here: job description, good/bad
  examples, binary filters (e.g. "worked as a backend engineer for 12+
  months"), which platforms to search, and search keywords. Autosaves as you
  type.
- **`roles/`** — a synced snapshot of the dashboard's data, read by the live
  server. See **Syncing roles** below.
- **`server/`** — the FastAPI app handling Slack's slash command +
  interactivity callbacks.
- **`sourcing.py`**, **`scoring.py`**, **`search_runner.py`** — the actual
  candidate sourcing (Apify) and scoring (Claude) pipeline.

## One-time setup

### 1. Deploy the server (Render)

1. Push this repo to GitHub (already done if you're reading this from the
   repo).
2. In [Render](https://render.com), New -> Blueprint -> connect this repo.
   It reads `render.yaml` and creates the web service automatically.
3. Under the service's **Environment** tab, add:
   - `ANTHROPIC_API_KEY`
   - `APIFY_API_KEY`
   - `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN` (from step 2 below — come back
     to this after creating the Slack app)
4. Note the service's URL, e.g. `https://hiring-sourcing-agent.onrender.com`.

**Free-tier caveat:** Render's free web services spin down after ~15 minutes
of no traffic and take 30-50s to wake back up. Slack requires a response to
a slash command within 3 seconds — a cold start will make `/search` fail
silently the first time it's used after a quiet period. If that happens in
practice, upgrade the service to Render's cheapest paid plan (~$7/mo), which
stays warm.

### 2. Create the Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) -> **Create New
   App** -> **From an app manifest** -> pick your workspace.
2. Paste in [slack-manifest.yaml](slack-manifest.yaml), but first replace
   both `REPLACE-WITH-YOUR-RENDER-URL` placeholders with your actual Render
   URL from step 1.
3. Create the app, then **Install to Workspace**.
4. Copy the **Signing Secret** (Basic Information page) and **Bot User OAuth
   Token** (OAuth & Permissions page, starts `xoxb-`) into Render's
   environment variables from step 1.4, and redeploy.
5. In Slack, invite the bot into #sourcing-search: `/invite @Sourcing Search`.

### 3. Add your first role

Open the [Sourcing Criteria dashboard](https://claude.ai/code/artifact/2e844088-02b3-459a-bc72-3ac0e31e0f89),
click **+ New role**, and fill in the job description, examples, and any
binary filters. Then ask Claude Code to sync it (see below) so the live
server can see it.

### 4. Try it

In #sourcing-search, type `/search`, pick the role, submit. Results post
into the channel once the search finishes (usually a couple of minutes).

## Syncing roles

The dashboard's data lives in the artifact's own database — the deployed
server can't reach that directly, so it reads from `roles/index.json` and
`roles/<id>.json` in this repo instead. Whenever you add or edit a role on
the dashboard, ask Claude Code to **"sync roles"**: it reads the dashboard's
database, rewrites those files, and commits + pushes — Render auto-redeploys
on push, so the change is live within a minute or two. This mirrors the
campaign-sync flow in the sibling creator-sourcing project.

Only roles with `status: active` are synced into `index.json` (what the
`/search` modal's dropdown shows) — archiving a role on the dashboard removes
it from the dropdown without deleting its criteria.

## Local testing

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real keys
export $(cat .env | xargs)

python search_runner.py <role_id>   # runs one search end-to-end, prints results (doesn't post to Slack)
```

To run the server locally against real Slack requests, tunnel it with
ngrok (`ngrok http 8000`) and point the Slack app's URLs at the ngrok URL
instead of Render while testing.

## Sourcing sources

All three are no-login/cookie-free Apify actors — none of them authenticate
as a real LinkedIn/Twitter/Instagram account, so there's no risk of an
account getting flagged:

- LinkedIn: `harvestapi/linkedin-profile-search`
- Twitter/X: `data_direct/twitter-users-scraper`
- Instagram: `khadinakbar/instagram-user-search-scraper`

Apify actor input schemas do change over time — if a search starts coming
back empty, check the actor's own "API" tab on apify.com for its current
input shape before assuming something else broke.

## Cost

Each `/search` run costs real Apify credits (LinkedIn search is the priciest
of the three) plus a small amount of Claude API usage for scoring. There's no
built-in spend cap — if usage volume grows, worth adding one before it's
run casually.
