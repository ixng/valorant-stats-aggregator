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
