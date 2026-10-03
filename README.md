# Valorant Stats Aggregator

One combined stat table across several Valorant accounts, plus per-account breakdowns, with splits by agent and by map.

Tracker.gg shows each account separately, so judging how I am actually playing means checking them one at a time. This pulls match data for every account I own into a local SQLite database and aggregates across all of them.

## Status

Work in progress, built milestone by milestone.

| Milestone | State |
|---|---|
| 1. API key and one successful request | done |
| 2. Config and identity resolution | done |
| 3. API client with rate limiting and retries | done |
| 4. Schema design | in progress |
| 5. Ingestion | not started |
| 6. Aggregation | not started |
| 7. Flask dashboard | not started |
| 8. Scheduled runs | not started |

## Stack

Python 3.12, SQLite, and Flask for the dashboard. Match data comes from the [HenrikDev unofficial VALORANT API](https://api.henrikdev.xyz), because Riot's official VALORANT API does not issue personal keys and a multi-account tracker is not an approved production use case.

Dependencies are `requests` and `python-dotenv`. Everything else is standard library: `sqlite3`, `tomllib`, `zlib`.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root with a key from the HenrikDev Discord:

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

Resolves every account in the config to its PUUID and caches it. Exits 0 when every account succeeded and 1 if any failed, so a scheduled run can be checked by its exit status.

## Design decisions

The decisions worth explaining, and why they went that way.

**Accounts are keyed on PUUID, not `name#tag`.** Riot IDs are changeable. Keying history on a display name means that the day I rename, new matches are stored under the new name while months of old matches sit under the old one. Queries then return only post-rename matches, with no error and numbers that look plausible. The PUUID never changes, so a rename updates one row and the history stays joined up.

**Resolution happens once per account and is cached.** A cached PUUID also means a rename cannot break ingestion, since the matches endpoint is keyed on PUUID and never needs the name again.

**All ten players in a match are stored, not just mine.** MVP, leaderboard position and win rate when stacking with the same teammates are all defined by comparison with the other nine players. None of them can be computed later from my own row.

**Team facts live in their own table.** Whether a team won is one fact per team, so it is stored once in `teams` rather than copied onto each of the five player rows, where copies could disagree. The same reasoning keeps round counts out of the performance rows.

**Raw responses are archived as a compressed BLOB.** First bloods live in the round-by-round kill events, which are most of a 500 KB response. Storing the raw response compressed keeps them recoverable without a schema for every round, because the API only returns recent matches and anything not captured at ingestion is gone for good.

**Stats are stored as raw inputs, not as ratios.** Score and rounds, not ACS. Combined ACS is total score over total rounds, so averaging per-match ACS values gives the wrong answer.

**Timestamps are stored in UTC and converted at display.** A stored local time is ambiguous at the autumn clock change, when 01:30 happens twice, and the information needed to disambiguate it is lost at write time.

**Writes are idempotent.** Ingestion re-fetches matches it has already seen on every run. Each table has a primary key that identifies the row naturally, `(match_id, puuid)` for a performance, and conflicts resolve with `DO NOTHING` because a finished match never changes.

**Every queue is stored and filtered in queries.** Deathmatch has no rounds and no winning team, so mixing it into K/D and ACS makes both meaningless. Excluding it from storage instead would make that choice permanent, so it is stored and filtered instead.

**Errors are typed by whether retrying can help.** A 404 on a Riot ID is permanent and needs the config fixed, so it raises immediately and that account is skipped while the rest continue. A 429 or a 5xx is transient, so it is retried with doubling backoff, honouring `Retry-After` when present and capped at 60 seconds. A rejected key stops the whole run, since every remaining request would fail the same way.

**Requests are spaced 2 seconds apart.** The free tier allows 30 requests a minute, which is one every 2 seconds. The spacing lives in the API client rather than in any caller, so every endpoint shares one limit.

## Data constraint

The API returns recent matches, not career history. Whatever it holds on the first ingestion run is the entire backfill that will ever exist, and nothing built later recovers matches that have aged out. That is why ingestion reliability matters here more than in a pipeline that can be re-run: a failed run that goes unnoticed for two weeks loses those two weeks permanently.

## Layout

```
accounts.toml      accounts to track
maps.toml          competitive maps prefilled into the lookup table
config.py          loads the config files and the API key
api.py             HTTP client: rate limiting, retries, typed errors
db.py              SQLite schema and queries
resolve.py         resolves accounts to PUUIDs
docs/api-notes.md  findings from testing the API by hand
```

## Notes

[docs/api-notes.md](docs/api-notes.md) records what testing the API showed, including the undocumented auth header, the 10 match per request cap, and the deathmatch response shape.
