# HenrikDev API Notes

Findings from testing the HenrikDev unofficial VALORANT API (`https://api.henrikdev.xyz`) by hand.

## Authentication

The API reads the key from the `Authorization` header, with no prefix:

```
Authorization: <key>
```

The OpenAPI spec doesn't declare any auth on its endpoints, even though every request needs a key. So the header name had to be found by testing.

### How it was confirmed

Three requests to `GET /valorant/v2/account/{name}/{tag}` for the same valid account, with only the header changed each time:

| Header sent | Status | What it shows |
|---|---|---|
| `Authorization: <key>` | 200 | The key was accepted and the account was found. |
| `X-API-Key: <key>` | 401 | The server doesn't read the key from this header. |
| None | 401 | The endpoint requires a key. So the 200 above came from the key, not from the endpoint being open. |

The Riot ID was valid in all three requests, so the header is the only thing that could explain the different results.

## Request notes

- A Riot ID `name#tag` is split into two parts of the path: `/account/{name}/{tag}`.
- Spaces in names must be percent-encoded as `%20`. A `+` only means a space in the query string. In the path, it's a literal plus sign.
- The key is never typed into a command. Load it into the shell with `read -s`, which keeps it out of shell history and off the screen, then reference it as a variable.

## Rate limiting

The free tier allows 30 requests per minute, and the API states the current position in
the window on every response:

```
ratelimit-policy: "per1min";q=30;w=60
x-ratelimit-limit: 30
x-ratelimit-remaining: 0
x-ratelimit-reset: 4
```

**It never sends `Retry-After`**, so a client that only looks for that header falls back to
guessing when the server has already told it the answer. `x-ratelimit-reset` is the number of
seconds until the window rolls over.

Pacing at exactly 2 seconds per request produces exactly 30 a minute, which leaves no
headroom: one retry, or a second run started inside the same minute, exceeds the quota. The
client therefore reads `x-ratelimit-remaining` and `x-ratelimit-reset` from every response and
waits for the reset when the quota is spent, rather than relying on spacing alone. Spacing
cannot know about requests made by an earlier run or by hand with the same key.

## Match history

- The matches endpoint returns at most **10 matches per request**. `size=5` returns 5 and
  `size=25` returns 10, so 10 is the endpoint's cap rather than the end of the history.
- `start` pages correctly, with no overlap between pages.
- The window holds **between 200 and 400 matches per account**, not the ~50 first assumed.
  That early figure came from a shell loop that read error responses as empty pages:
  `jq '.data | length'` prints `0` for `null`, so a rate-limit error and the end of the
  history looked identical. An error and an empty page have to be distinguished explicitly.
- A page past the end of the history returns **`data: null`, not `[]`**, so ingestion must not
  assume a list.

### One match in the history returns 502 permanently

Fetching one particular page of an account's history fails with 502 every time, while every
page either side succeeds:

```
page 4 (start=40): 10 matches
page 5 (start=50): 502 after 3 attempts
page 6 (start=60): 10 matches
```

Refetching that range one match at a time with `size=1` isolates it: nine offsets return a
match and one fails. So the cause is a single match whose data the API cannot serialise, not a
problem with the account or the page boundary.

Two consequences for ingestion:

- **A failed page must not abandon the account**, or every older match behind it becomes
  permanently unreachable. The page is skipped and the loop continues, with a guard that stops
  the account after several consecutive failures so a genuine outage still gives up.
- **The bad match cannot be identified and skipped by id**, because the request that would
  reveal its `match_id` is the one that fails. Its offset also moves as new matches are played.
  So the recovery has to be positional and recomputed on each run: on a page failure, retry the
  ten offsets individually and save the nine that work.

## Queue filtering

`metadata.queue` has three fields, and the one to filter on is `id`.

| `queue.id` | `queue.mode_type` | `queue.name` |
|---|---|---|
| `competitive` | Standard | Competitive |
| `deathmatch` | Deathmatch | Deathmatch |
| `hurm` | Team Deathmatch | Team Deathmatch |
| `skirmish_2v2` | Skirmish | *(null)* |
| *(empty string)* | Skirmish | Custom Game |

- **`mode_type` does not separate competitive from unrated.** Competitive returns
  `mode_type: "Standard"`, and unrated is the same mode, so it shares that value.
- **A custom game has an empty `queue.id`.** Ingestion substitutes `custom` so the column stays
  non-empty and the foreign key to `queues` resolves. Custom games are then excluded by the
  queries, the same way deathmatch is.
- **`skirmish_2v2` has a null `queue.name`**, so the stored name falls back to `mode_type`.

## Other response notes

- **Deathmatch reuses `teams[]` differently:** one entry per player, each with a unique
  `team_id`, `rounds_won` equal to that player's kills, and `rounds_lost` always 0. Competitive
  matches have 18 to 26 rounds; deathmatch and team deathmatch have a `rounds` array of
  length 1.
- **First bloods are not a field.** They come from the match's top-level `kills` array, where
  each entry has `round`, `time_in_round_in_ms`, `killer.puuid` and `victim.puuid`. The first
  blood of a round is the earliest kill in it.
- **Kill events arrive in `(round, time)` order**, verified across 80 matches, but nothing
  documents that, so the first-blood calculation sorts rather than relying on it.
- **Ties are real:** 6 rounds out of 80 matches had two kills at the same millisecond.
- **`GET /valorant/v1/content?locale=en-US`** returns every map, agent and game mode, with ids
  matching the match metadata. The 28 map entries include practice ranges and internal maps,
  and two different maps are both named "The Range", so map names are not unique.
