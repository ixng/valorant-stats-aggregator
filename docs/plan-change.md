# Plan change: from a single-user tool to a multi-user web app

Written 4 November 2026, after milestone 6 and the Cloudflare deployment were finished.

The project was specified as a local tool: Python scripts, SQLite, and a Flask dashboard
for one person's own accounts. It is now intended to become a web app where any user can
sign in and track whichever Riot accounts they want to compare.

This document records what changed, why, and what each change costs. It is not a
specification. The original brief's milestones 1 to 6 are unchanged and already built.

---

## 1. Django replaces Flask for the web layer

The brief named Flask. With a login page in scope, Django is the better choice.

**Why:** password hashing, session handling, CSRF protection, password reset and an admin
interface are all required the moment users exist, and all four ship with Django. Writing
authentication by hand is the one part of a web app where a mistake is dangerous rather
than untidy, and Flask leaves it to the developer. The brief chose Flask when there were
no users, which was correct then.

**Positives**

- Authentication is configuration rather than code, so the risky part is handled by a
  library that is widely reviewed.
- Migrations come with it, which the current project does not have at all. The schema is
  currently created by `CREATE TABLE IF NOT EXISTS` and changed by hand.
- The admin interface gives a working way to inspect and fix data with no code written.

**Negatives**

- Django is a much larger framework to learn than Flask, and most of it is not needed here.
- It imposes a project layout, so the current flat set of modules has to move.
- It is a deliberate deviation from the brief, which has to be explained rather than
  assumed.

---

## 2. The app supports many users, each tracking their own set of accounts

One user may track several Riot accounts, and different users may track different sets.

**Why:** this is the actual goal of the change. Comparing accounts is only interesting to
someone who holds more than one, and the tool is no use to anyone else while the accounts
are hardcoded in `accounts.toml`.

**Positives**

- `accounts.toml` stops being a configuration file edited by hand and becomes rows a user
  controls through the interface.
- The aggregation functions already take an optional PUUID filter, so "the accounts this
  user tracks" is a small extension of work already done rather than a rewrite.

**Negatives**

- Everything gains an access-control question that did not exist before.
- Signup becomes slow, because a new account's history has to be fetched before the
  dashboard has anything to show.

---

## 3. Matches stay global; only the user-to-account link is per user

`matches`, `performances`, `teams`, `maps`, `agents` and `queues` keep no user column. One
new table records which accounts a user tracks.

**Why:** a match is a fact about the world, not about a user. Two users tracking the same
Riot account must not cause the same match to be stored twice, because duplicate rows for
one real event make every aggregate wrong. The existing primary keys, `match_id` and
`(match_id, puuid)`, already encode this: they identify the event and the player in it,
with no room for a user. Adding a user column would mean changing those keys and giving up
the idempotency the ingestion relies on.

**Positives**

- Storage grows with matches played, not with users times matches.
- A user adding an account another user already tracks gets its history immediately, with
  no API calls.
- The ingestion code needs no change at all. It already writes world facts.

**Negatives**

- One user's ingestion fills a table every user reads, so a bad write affects everyone.
- "Which user caused this row to exist" is no longer answerable, which matters if an
  account ever has to be removed along with its data.

---

## 4. Ingestion becomes a single background worker fed by a queue

The web app never calls the Valorant API. Adding an account writes a row saying it needs
ingesting, and one separate process does the work.

**Why:** two reasons, and the first is a correctness bug rather than a preference.

The rate limiter in `api.py` keeps `_last_request_at` and `_quota_remaining` as
module-level variables. Django runs several worker processes, and each one would hold its
own copy, so each would believe it owned the whole 30 requests per minute. The quota is per
API key and does not multiply with processes, so this produces 429s immediately. One
consumer makes that state correct again.

Second, ingesting one account is 200 to 400 matches at ten per request, paced at 2.2
seconds, so roughly 90 seconds. That cannot happen inside an HTTP request.

**Positives**

- The existing limiter becomes correct without being rewritten.
- The work has a defined order and a visible backlog, so a user can be told their position
  and a rough wait.
- Whether ingestion is running is a question about one process.
- Milestone 8 was going to create a scheduled process anyway, so this is the same work
  arriving earlier.

**Negatives**

- A second process to deploy, supervise and restart.
- The interface needs a pending state and a way to show failure, which a blocking request
  would not have needed.
- The queue is a new table with its own states, retries and stuck-row problems.

---

## 5. The rate limiter stays in one process rather than moving to Redis

A shared Redis-backed limiter was considered and rejected.

**Why:** distributing a limiter buys throughput, and there is no throughput to gain. The
ceiling is one request every two seconds, which a single process satisfies while idle. The
cost is real: a shared counter needs atomic operations or it races, a process that reserves
a slot and crashes leaks quota, and `time.monotonic()` is not comparable across processes so
the existing waiting logic would have to be rewritten against wall clock. Redis also becomes
a dependency on the ingestion path, where being unreachable forces a choice between ignoring
the limit and stopping entirely.

It would also work against the closed-loop design. The limiter reads
`x-ratelimit-remaining` and `x-ratelimit-reset` from every response, and split across
processes each one sees only its own responses.

**Positives**

- No new infrastructure, and no new failure mode on the ingestion path.
- The code that already works keeps working.

**Negatives**

- Ingestion throughput is capped at one process, so it cannot be scaled out later without
  revisiting this.
- If the project ever needs several independent callers of the API, this decision has to be
  undone.

**Note:** limiting inbound traffic to the app, so one user cannot hammer it, is the opposite
problem and Redis is the right answer there. The difference is that every caller of the
Valorant API is under our control, and users are not.

---

## 6. Django's ORM is used for users and accounts; aggregation stays raw SQL

Models for authentication, accounts and the queue. The aggregation queries in `db.py`
remain hand-written SQL, run through Django's database connection.

**Why:** the ORM earns its place for CRUD and migrations. It does not for the aggregation.
`COUNT(DISTINCT CASE WHEN t.won = 1 THEN m.match_id END)` with four joins and an optional
filter is clearer as SQL than as any ORM expression of it, and the two-grain counting rule
is easier to see and to defend in SQL. ORM for records and raw SQL for analytics is a
normal production split, not a compromise.

**Positives**

- Migrations and the admin interface for the parts that change shape.
- The schema reasoning and the query work stay visible rather than being hidden behind
  generated SQL.
- `EXPLAIN QUERY PLAN` still applies to queries that exist as written text.

**Negatives**

- Two ways of reaching the database in one codebase, which has to be a stated rule rather
  than a habit.
- The raw queries are not checked by Django's migration system, so a column rename can
  break them silently.

---

## 7. SQLite during development, PostgreSQL once deployed

Keep SQLite locally. Move to Postgres when the app is hosted.

**Why:** the limitation that matters is not concurrency. SQLite allows one writer at a
time, and with a single ingestion worker and a small read load that is sufficient for a
long time. The limitation is deployment: a login page means the app lives somewhere other
than a laptop, and a SQLite file has to sit on storage that survives a restart. Several
cheap hosts provide an ephemeral filesystem, and `valstats.db` holds the only copy of two
years of history. Postgres is Django's default in production, so moving later is a settings
change plus a data migration done once.

The existing SQL is more portable than most. `ON CONFLICT ... DO UPDATE` and the row-value
comparison `(a, b) = (c, d)` both work in Postgres. What does not carry over is every
`PRAGMA`, including `foreign_keys = ON`, which Postgres does not need because foreign keys
are always enforced.

**Positives**

- No migration work until there is a reason for it.
- Development stays a single file with no server to run.
- Postgres removes the single-writer limit before it is ever reached, and gives real
  concurrent access for a hosted app.

**Negatives**

- Two databases to support, so anything SQLite-specific has to be avoided from now on.
- The production database behaves differently from the development one, which is a class of
  bug that only appears after deployment.
- Postgres has to be run somewhere, which costs money or a free tier with its own limits.

---

## 8. The Cloudflare Worker stays scoped to the owner's own accounts

The published API continues to serve only the three original accounts, not every user's.

**Why:** it currently publishes every aggregate in the database because all of them belong
to one person. Once other users exist, "which aggregates are public" needs an answer, and
publishing everyone's by default is not it. Keeping the Worker as a personal public profile
keeps that question closed.

**Positives**

- No access control is needed in the Worker, which stays a read-only table and three
  queries.
- The deployed URL keeps working and keeps meaning what it says.

**Negatives**

- The app and the published API diverge, so two things compute the same statistics.
- If users ever want public profiles, this has to be designed properly rather than extended.

---

## 9. The order of work changes: dashboard first, authentication last

Milestone 7 is built as a single-user read-only dashboard with no login. Milestone 8
follows. Authentication and multi-user support come after both.

**Why:** each stage then ends with something that works. Building authentication first
produces several weeks in which the honest answer to "can I see it?" is no. The background
worker that multi-user support requires is the same process milestone 8 creates, so doing
milestone 8 first means the hard part of multi-user is already in place.

**Positives**

- There is a demonstrable project at every point.
- The queue arrives as part of work already planned rather than as new scope.
- The data stops being a snapshot earlier, which the published API needs.

**Negatives**

- The dashboard is written once without users and then adjusted for them.
- Multi-user support is deferred, so the stated goal of the change is the last thing to
  arrive.

---

## What has not changed

- The ingestion pipeline, the extractor functions and `save_match`.
- The schema's core tables and every constraint on them.
- `api.py`, including the retry taxonomy and the closed-loop limiter.
- The aggregation queries and the decision to store raw sums rather than ratios.
- The published Cloudflare API and its data boundary.

The change is a new layer above the existing project, not a rewrite of it.

---

## Overall assessment

**The strongest argument for it:** the project becomes useful to someone other than its
author, which is the difference between a script and a product. It also forces three
problems worth having solved, namely a shared resource under a fixed quota, work that
cannot run inside a request, and a data model where facts are shared but access is not.

**The strongest argument against it:** it is weeks of work, and the parts that make the
current project worth discussing are already built. A finished small project is worth more
than an ambitious half-built one, and the risk is spending the time without reaching a
state that works.

**The decision:** proceed, but in the order in section 9, and treat multi-user support as a
second phase with its own completion point rather than as the continuation of the first.
