# Valorant Stats Aggregator

[![CI](https://github.com/ixng/valorant-stats-aggregator/actions/workflows/ci.yml/badge.svg)](https://github.com/ixng/valorant-stats-aggregator/actions/workflows/ci.yml)

One combined stat table across several Valorant accounts, plus per-account breakdowns, with splits by agent and by map.

I made this because Tracker.gg shows each account separately, so there is inconvenience in having multiple tabs open when I am trying to check multiple accounts all at once (definitely NOT because I have multiple smurf accounts). This pulls the match data for every account I own into a local SQLite database and aggregates across all of them. I plan to eventually make Multi-user accounts with Django, which include logins, linking accounts, background syncing through one shared rate limiter. To turn this into an actual small scale product.

Right now the aggregates are published as a read-only JSON API on Cloudflare Workers, backed by D1, as proof the aggregation and the API requesting works. Heres the link: **https://valstats-api.ixng.workers.dev** (also talked about below where it is explained in more detail).

---

## Contents

- [Status](#status)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Tests and CI](#tests-and-ci)
- [Design Decisions](#design-decisions)
- [Deployed API](#deployed-api)
- [Verification](#verification)
- [Data constraints](#data-constraints)
- [Project layout](#project-layout)
---

## Status

Work in progress! Initially I structured my project in milestones as shown below. However, whilst working on the project I have made many changes as continuously adding CI tests to make sure there are no errors on merges, and even plan to use Django's ORM for records whilst continuing to use raw SQL for aggregation, and even add per-user account tracking, Postgres for storage and a real server I can use this application on.

OLD IDEA (with which what is done and what is not/ in progress)
| ACT | State |
|---|---|
| 1. API key and one successful request | done |
| 2. Config and identity resolution | done |
| 3. API client with rate limiting and retries | done |
| 4. Schema design | done |
| 5. Ingestion | done |
| 6. Aggregation | done |
| 7. Flask dashboard | aborted |
| 8. Scheduled runs | aborted |

With user accounts now in the scope, the web layer is written once in Django instead allowing: authentication, migrations and an admin interface are configuration rather than code.

NEW ADDITIONS! Which progress from Milestone 6 onwards
| SEASON | State |
|---|---|
| 1. Capture the data already archived but not stored | in progress |
| 2. Django, including the web interface | not started |
| 3. User accounts and queued ingestion | not started |
| 4. Deployment and scheduled runs | not started |

## Requirements

- Python 3.12 or later, for `tomllib`
- An API key from the [HenrikDev unofficial VALORANT API](https://docs.henrikdev.xyz/valorant/general)

Two runtime dependencies, `requests` and `python-dotenv` . Everything else is standard library: `sqlite3`, `tomllib`, `zlib`.

Django for the web layer once it exists.

Match data comes from the [HenrikDev unofficial VALORANT API](https://docs.henrikdev.xyz/valorant/general), because Riot's official VALORANT API does not issue personal keys and a multi-account tracker is not an approved production use case.


---

## Installation

```bash
git clone https://github.com/ixng/valorant-stats-aggregator.git
cd valorant-stats-aggregator
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

**The API key.** Create a `.env` file in the project root:

```
HENRIK_KEY=your-key-here
```

`.env` is gitignored, and make sure the key is never written to source, logs or error messages.

**The accounts to track.** List them in `accounts.toml`:

My account for example:

```toml
[[accounts]]
name = "donner kebab"
tag = "bossm"
```

**The map lookup table.** `maps.toml` holds the competitive maps that get prefilled, so a map with no matches yet appears in a breakdown instead of being left out. Ingestion still inserts any other map it meets, so no match ends up pointing at a missing row.

A malformed config raises `ConfigError` with the file, the entry number and the field at fault, and nothing catches it: as a bad config should stop a run with a sentence rather than a traceback.

---

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root with a key from the HenrikDev Discord (https://api.henrikdev.xyz/dashboard/):

```
HENRIK_KEY=your-key-here
```

`.env` is gitignored and the key is never written to source, logs or error messages.

List the accounts to track in `accounts.toml`:

```toml
[[accounts]]
name = "donner kebab"
tag = "bossm"
```

`maps.toml` holds the competitive maps that get prefilled into the map lookup table, so the dashboard can show a map with no matches yet instead of leaving it out.

---

## Usage

### Resolve accounts to PUUIDs

```bash
python resolve.py
```

Resolves every account in the config and caches the result. Exits 0 when every account succeeded and 1 if any failed, so a scheduled run can be checked by its exit status.

### Fetch and store matches

```bash
python ingest.py
```

Stops at the first page whose matches are all already stored, which makes a routine run take about five seconds rather than ten minutes.

```bash
python ingest.py --full
```

Sweeps each account's entire window instead, which is how the stop rule gets checked for gaps.

### Print the stats

```bash
python report.py
```

```bash
python report.py --split agent
python report.py --split map
python report.py --account "donner kebab#bossm"
python report.py --queue competitive
```

Reads the local database only and makes no API calls.

### Publish the aggregates

```bash
python export_d1.py
npx wrangler d1 execute valstats --remote --file worker/stats.sql
```

---

## Tests and CI

28 tests, run by GitHub Actions on every push and every pull request along with
`ruff` and `black --check`.

```bash
pytest -v
```

| File | Tests | What it covers |
|---|---|---|
| `tests/test_config.py` | 13 | Every way a config file can be malformed |
| `tests/test_db.py` | 8 | The per-match counting rule, the queue filter, idempotency, the split allowlist, the foreign key pragma |
| `tests/test_stats.py` | 7 | The five formulas against figures worked out by hand, that no rounding happens, and the zero-denominator cases |

The tests need no database and no API key. The config tests read fixtures committed to the repository, and the database tests build their own in-memory data base from the real schema, so that no cross-test contamination can happen.

---

## Deployed API

The aggregates are published as a read-only JSON API on Cloudflare Workers, backed by D1:

**https://valstats-api.ixng.workers.dev**

| Route | Returns |
|---|---|
| `/` | the accounts held, with ready-made URLs for each view |
| `/stats/{account}` | that account's overall totals and rates |
| `/stats/{account}/agent` | one entry per agent |
| `/stats/{account}/map` | one entry per map |

`{account}` is `combined` or a percent-encoded Riot ID, so `donner%20kebab%23bossm`.

**Ingestion stays local.** The Worker holds no API key and calls no third-party service. `export_d1.py` reads the database through the same functions `report.py` uses and writes the derived totals as SQL, which wrangler pushes to D1. No per-match rows and no raw responses are published, so the nine other players in each match never leave the machine.

**Rates are computed in the Worker, not stored**, for the same reason the local database stores raw sums: a stored percentage cannot be re-aggregated. The cost is that the derivation exists twice, in `stats.py` and in `worker/src/index.ts`, and the two have to be changed together.

---

## Design decisions

The key decisions I had to make during this project listed as bullet points:

**Accounts are keyed on PUUID, not `name#tag` -** Riot IDs are changable, so keying the history of a players matches on a display name means the day a rename happens new matches are only stored under the new name, and the old matches sit under the old name. Aggregation queries then become inaccurate. The puuid never changes so a rename only updates the name and tag of the accounts row.

**Resolution happens once per account and is cached -** A cached PUUID means that a rename doesn't break ingestion, since the matches endpoint is keyed on PUUID and the name is never needed again.

**All ten players in a match are stored, not just mine -** Player stats such as who is the MVP and leaderboard position are all defined by comparing each player with another, and cannot be computed from only one player. A problem I ran into was when I tried to combine the two stats of players who had played in the same game, so it was needed to store each player to check for that edge case.

**Team facts live in their own table -** Only because it contains information on weather a team won the match, how many rounds were won or lost. Better than storing the information per player as the player can have a foreign key which maps to a row. Only stored twice per match.

**Raw responses are archived as a compressed BLOB -** Each response includes round-by-round kills, and even the co-ordinates of the players on the map which might be needed later incase I need it for new features, all of this adds up to about 500 KB of storage. Storing the raw response compressed keeps this information recoverable without a schema for every round. Another good reason is because the API only returns recent matches and anything that is not captured at ingestion is gone for good.

**Derived numbers keep full precision, and rounding happens at display -** Aggregation layer returns non-rounded values, such as a win rate of 51.73913, and I have decided to keep the rounding separate as it means the number can no longer be used to calculate other statistics in the future. So the rounding only takes place in the terminal output and the future dashboard templates.

**The combined view counts matches and not player appearances -** After testing the edge-case where a user's connected accounts share the same match, I found out that distinct 493 competitive matches were played, and 615 appearances were documented , meaning there were some matches which had more than one of the connected account playing in that game. So instead of counting player appearances we count the number of distinct matches in the performances table.

**Timestamps are stored in UTC and converted at display -** Rare edge case where, account data showed games played when day-light saving happened this autumn (October 2026), it was recorded that two games were played at 01:30. As a result the information to disambiguate was lost at write time. They are stored as ISO 8601 text, which sorts lexicographically in the same order as it sorts chronologically. A date range filter is therefore just a plain string comparison with no parsing needed.

**Writes are idempotent -** Ingestion re-fetches matches it has already seen on every run, because a completed match is immutable, so even if a difference in a few stats rows changing is tried to be ingested again with the same primary key |`(match_id, puuid)`| nothing will change.

**Every queue is stored and filtered in queries -** A deathmatch has no rounds and no winning team, so ingesting the kill death ratio and the average combat score infects the players stats with bad and inaccurate data. 

**Config errors are typed whether retrying can help or not -** Errors such as a 404 error on a Riot ID is a permanent issue and needs the config fixed, so it raises immediately and that account is skipped while the rest continue. A 429 or a 5xx error is transient, so it is retried without doubling backoff. A rejected key stops the whole run, since every remaining request will fail without a valid API key.

**Rate limiting reads the server's own counters rather than only pacing -**The free tier for the API allows 30 requests per minute, and a nice feature I found is that the API reports the remaining quota and the seconds until that window resets on every response. The current client spaces requests 2.2 seconds apart, which is 27 a minute rather than exactly 30 to allow breathing space for each request. Additionally, it waits for the however long the `Retry-After` header states before making another request.

---

## Verification

The aggregation was checked against Tracker.gg for one account over one act, ten competitive matches.

| metric | this project | Tracker.gg |
| --- | --- | --- |
| matches | 10 | 10 |
| wins | 6 | 6 |
| win rate | 60.0% | 60.0% |
| K/D | 0.97 | 0.97 |
| ACS | 194.1 | 194.1 |
| headshot % | 21.8% | 21.8% |
| ADR | 129.7 | 129.4 |

Six of the seven agree exactly. ADR differs by 0.3.

The cause is damage accounting rather than arithmetic. ACS divides by the same round count and agrees to the decimal, so the denominator is right and the difference is in the damage total. Summing the round-by-round damage events in the archived responses shows that the match-level `damage.dealt` field counts damage dealt to teammates: across the 50 archived matches it totals 129,192 against 128,825 for enemy damage alone, 0.285% higher. The observed ADR gap is 0.24%, the same direction and close to the same size. Tracker appears to count enemy damage only.

An extra 367 damage over those 50 matches is still unexplained, which is 0.03%. The archive holds 50 of that account's 184 matches, so it cannot be settled from what is stored.

---

## Data constraints

The API serves a window of recent matches rather than career history. Measured across three accounts, that window holds 200 to 400 matches each, reaching back to August 2024.

An earlier version of this section claimed the first ingestion run captured the only backfill that would ever exist. That was wrong. It came from a shell loop that read rate-limit error bodies as empty pages, because `jq '.data | length'` prints `0` for `null`, so an error and the end of the history looked identical.

Matches do leave the window eventually, so each raw response is still archived at ingestion and `load_archive` can replay saved pages with no network calls. A run that fails unnoticed for two weeks is now recoverable, because those matches are still inside the window. Reliability of the data ingested matters since a silent partial failure produces aggregates that are wrong without looking wrong.

---

## Project layout

**The pipeline**, in the order the data moves through it:

| | |
|---|---|
| `config.py` | loads the config files and the API key |
| `api.py` | HTTP client: rate limiting, retries, typed errors |
| `resolve.py` | resolves accounts to PUUIDs |
| `ingest.py` | fetches matches and stores them |
| `db.py` | SQLite schema, writes and aggregation queries |
| `stats.py` | turns the stored sums into rates |
| `report.py` | prints the stats in a terminal |
| `export_d1.py` | writes the aggregates out as SQL for the deployed API |

**Everything else:**

| | |
|---|---|
| `accounts.toml`, `maps.toml` | the accounts to track, and the map lookup table |
| `worker/` | the Cloudflare Worker and its D1 schema |
| `tests/` | pytest suite, with one-defect config fixtures |
| `.github/workflows/` | the CI workflow |
| `docs/api-notes.md` | findings from testing the API by hand |
| `pyproject.toml`, `requirements*.txt` | pytest configuration and pinned dependencies |

If you are reading the code, start with `ingest.py` for how matches are fetched and stored, then `db.py` for the aggregation queries and the counting rule they implement.

---
