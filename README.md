# Valorant Stats Aggregator
[![CI](https://github.com/ixng/valorant-stats-aggregator/actions/workflows/ci.yml/badge.svg)](https://github.com/ixng/valorant-stats-aggregator/actions/workflows/ci.yml)
One combined stat table across several Valorant accounts, plus per-account breakdowns, with splits by agent and by map.

I made this because Tracker.gg shows each account separately, so there is inconvenience in having multiple tabs open when I am trying to check multiple accounts all at once (definitely NOT because I have multiple smurf accounts). This pulls the match data for every account I own into a local SQLite database and aggregates across all of them. I plan to eventually make Multi-user accounts with Django, which include logins, linking accounts, background syncing through one shared rate limiter. To turn this into an actual small scale product.

Right now the aggregates are published as a read-only JSON API on Cloudflare Workers, backed by D1, as proof the aggregation and the API requesting works. Heres the link: **https://valstats-api.ixng.workers.dev** (also talked about below where it is explained in more detail).

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
| 7. Flask dashboard | in progress |
| 8. Scheduled runs | not started |

With user accounts now in the scope, the web layer is written once in Django instead allowing: authentication, migrations and an admin interface are configuration rather than code.

NEW ADDITIONS! Which progress from Milestone 6 onwards
| SEASON | State |
|---|---|
| 1. Capture the data already archived but not stored | in progress |
| 2. Django, including the web interface | not started |
| 3. User accounts and queued ingestion | not started |
| 4. Deployment and scheduled runs | not started |

## Stack

Python 3.12 and SQLite, with Django for the web layer once it exists. Match data comes from the [HenrikDev unofficial VALORANT API](https://docs.henrikdev.xyz/valorant/general), because Riot's official VALORANT API does not issue personal keys and a multi-account tracker is not an approved production use case.


Dependencies are `requests` and `python-dotenv`. Everything else is standard library: `sqlite3`, `tomllib`, `zlib`.

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

## Usage

```bash
python resolve.py
```

Resolves every account in the config to its PUUID and caches it. Exits 0 when every account succeeded and 1 if any failed, so a scheduled run can be checked by its exit status, when made later on.

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

## Design decisions

The decisions I had to make during this project and why they went that way (Where I made every decision and Claude helped Structure my explanations):

**Accounts are keyed on PUUID, not `name#tag`.** Riot IDs are changeable. Keying history on a display name means that the day I rename, new matches are stored under the new name while months of old matches sit under the old one. Queries then return only post-rename matches, with no error and numbers that look plausible. The PUUID never changes, so a rename updates one row and the history stays joined up.

**Resolution happens once per account and is cached.** A cached PUUID also means a rename cannot break ingestion, since the matches endpoint is keyed on PUUID and never needs the name again.

**All ten players in a match are stored, not just mine.** MVP, leaderboard position and win rate when stacking with the same teammates are all defined by comparison with the other nine players. None of them can be computed later from my own row.

**Team facts live in their own table.** Whether a team won is one fact per team, so it is stored once in `teams` rather than copied onto each of the five player rows, where copies could disagree. The same reasoning keeps round counts out of the performance rows.

**Raw responses are archived as a compressed BLOB.** First bloods live in the round-by-round kill events, which are most of a 500 KB response. Storing the raw response compressed keeps them recoverable without a schema for every round, because the API only returns recent matches and anything not captured at ingestion is gone for good.

**Stats are stored as raw inputs, not as ratios.** Score and rounds, not ACS. Combined ACS is total score over total rounds, so averaging per-match ACS values gives the wrong answer.

**Derived numbers keep full precision, and rounding happens at display.** The aggregation layer returns a win rate of 51.73913, not 51.7. A rounded value cannot be combined with anything further, and rounding inside the function means its tests have to match the rounding rather than the arithmetic. Formatting to one or two decimal places belongs to the terminal output and the dashboard templates.

**The combined view counts matches, not appearances.** The tracked accounts queue together, so 493 competitive matches produce 615 performance rows. Counting rows would weigh a stacked match twice and report 615 matches played, so `matches` and `wins` count distinct match ids. The per-round totals stay per appearance, because combined ACS is the total score of every appearance divided by the rounds those appearances covered. This is unambiguous only because every shared match has the accounts on the same team. An account that played against the others would make "did we win" two different facts for one match.

**Timestamps are stored in UTC and converted at display.** A stored local time is ambiguous at the autumn clock change, showed when 01:30 happens twice, and the information needed to disambiguate it is lost at write time. They are stored as ISO 8601 text, which sorts lexicographically in the same order as it sorts chronologically. A date range filter is therefore a plain string comparison with no parsing, and `started_at >= '2026-09-01'` selects everything from that day onward. Ranges are written half open, lower bound inclusive and upper bound exclusive, because `<= '2026-10-24'` would drop every match played on the 24th.

**Writes are idempotent.** Ingestion re-fetches matches it has already seen on every run. Each table has a primary key that identifies the row naturally, `(match_id, puuid)` for a performance, and conflicts resolve with `DO NOTHING` because a finished match never changes. `DO NOTHING` keeps the stored row rather than the incoming one, so re-ingesting a match whose stats differ silently discards the new values. That is the correct behaviour here and only here: a completed match is immutable, so a difference means the stored copy is right and the new one is noise. It would be the wrong resolution for anything still in progress, where the later read is the accurate one and `DO UPDATE` would be needed instead.

**Every queue is stored and filtered in queries.** Deathmatch has no rounds and no winning team, so mixing it into K/D and ACS makes both meaningless. Excluding it from storage instead would make that choice permanent, so it is stored and filtered instead.

**Errors are typed by whether retrying can help.** A 404 on a Riot ID is permanent and needs the config fixed, so it raises immediately and that account is skipped while the rest continue. A 429 or a 5xx is transient, so it is retried with doubling backoff, honouring `Retry-After` when present and capped at 60 seconds. A rejected key stops the whole run, since every remaining request would fail the same way.

**Rate limiting reads the server's own counters rather than only pacing.** The free tier allows 30 requests a minute, and the API reports the remaining quota and the seconds until the window resets on every response. The client spaces requests 2.2 seconds apart, which is 27 a minute rather than exactly 30, and additionally waits for the advertised reset once the quota is spent. Spacing alone cannot know about requests made by an earlier run or by hand with the same key. The limiter lives in the API client rather than in any caller, so every endpoint shares one limit. The API never sends `Retry-After`, so a client that waits only for that header is guessing when the server has already given it the answer.

## Data constraint

The API serves a window of recent matches rather than career history. Measured across three accounts, that window holds 200 to 400 matches each, reaching back to August 2024.

An earlier version of this section claimed the first ingestion run captured the only backfill that would ever exist. That was wrong. It came from a shell loop that read rate-limit error bodies as empty pages, because `jq '.data | length'` prints `0` for `null`, so an error and the end of the history looked identical.

Matches do leave the window eventually, so each raw response is still archived at ingestion and `load_archive` can replay saved pages with no network calls. A run that fails unnoticed for two weeks is now recoverable, because those matches are still inside the window. Reliability of the data ingested matters since a silent partial failure produces aggregates that are wrong without looking wrong.

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

A residual 367 damage over those 50 matches is still unexplained, which is 0.03%. The archive holds 50 of that account's 184 matches, so it cannot be settled from what is stored.

## Layout

```
accounts.toml      accounts to track
maps.toml          competitive maps prefilled into the lookup table
config.py          loads the config files and the API key
api.py             HTTP client: rate limiting, retries, typed errors
db.py              SQLite schema, writes and aggregation queries
resolve.py         resolves accounts to PUUIDs
ingest.py          fetches matches and stores them
stats.py           turns the stored sums into rates
report.py          prints the stats in a terminal
export_d1.py       writes the aggregates out as SQL for the deployed API
worker/            the Cloudflare Worker and its D1 schema
docs/api-notes.md  findings from testing the API by hand
```

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

