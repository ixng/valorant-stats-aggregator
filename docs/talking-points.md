# Talking Points

Decisions from this project that are worth explaining out loud, with the evidence
that settled each one. Written for interviews, where the question is usually not
"what does your project do" but "why is it that way".

## Testing

### A test whose assertion survives its own setup failing is not a test

Every test in `tests/test_db.py` asserts a per-appearance number before it asserts
the match count.

The aggregation rule is that two tracked accounts in one match count as one match
but contribute both players' stats. So the obvious test is `matches == 1`. That
assertion is satisfied two ways: by two performance rows collapsing to one match,
which is the behaviour under test, and by only one row ever being inserted, which
is the setup silently failing. Asserting `kills == 40` first distinguishes them.

The same reasoning appears three more times. The untracked-player test asserts
three rows were stored before asserting two were counted. The queue-filter test
queries the deathmatch explicitly to prove it exists before asserting it is
excluded from the default view.

### `pytest.raises(match=...)` is load-bearing in one test and noise in another

In the foreign key test it is load-bearing. `sqlite3.IntegrityError` also covers
primary key collisions and NOT NULL violations, so a typo in the test's own insert
dict would raise the same class and the test would pass while proving nothing
about foreign keys. Pinning `FOREIGN KEY constraint failed` is what makes the
assertion specific.

In the zero-division tests it is noise. All four zero denominators produce the
identical string `division by zero`, because CPython writes that message, not the
project. A `match=` that cannot distinguish the case it is in adds nothing.

### A regex that looks like a literal

`pytest.raises(match=...)` passes its argument to `re.search`. Two messages in this
project contain square brackets:

- `no [[accounts]] entries found`
- `unknown split 'agents', expected one of ['agent', 'map']`

`[[accounts]` and `['agent', 'map']` are character classes, so the brackets are
never matched literally and the pattern silently fails against a string that
visibly contains it. One of these produced a `FutureWarning: Possible nested set`,
which was the only clue. `re.escape` fixes it, but the better fix is usually to pin
a shorter substring: the part of a message a caller could rely on, not the part
that is a debugging aid and changes whenever the valid-value list grows.

### Choosing inputs so a test is capable of failing

`stats.derive` must not round, because a rounded value cannot be combined further.
The test for it is worthless on convenient numbers: `100 * 5 / 10` is `50.0`, and
`round(50.0, 1)` is also `50.0`, so the test passes whether or not rounding was
added. The criterion is that each ratio must differ from its own rounded form,
checked as `value != round(value, 1)`, which forced a deliberately awkward input
row: 255 wins in 493 matches, 4001 score over 21 rounds, 101 total shots.

### Float arithmetic is not associative, so the expectation has to mirror the code

`derive` computes `100 * wins / matches`. Writing the expectation as
`100 * (wins / matches)` is a different computation, because the intermediate
result is rounded to 53 bits before the next operation:

| wins/matches | `100 * w / m` | `100 * (w / m)` | equal |
|---|---|---|---|
| 255/493 | 51.724137931034484 | 51.724137931034484 | yes |
| 1/3 | 33.333333333333336 | 33.33333333333333 | no |
| 2/7 | 28.571428571428573 | 28.57142857142857 | no |

A test written the second way passes on 255/493 by luck and breaks later for a
reason unrelated to the code under test.

### Once `==` is asserted, the matching `!=` carries no information

The pooled-versus-averaged test asserts that combined ACS is total score over
total rounds and not the mean of per-match figures. Given
`derived == pooled_acs`, a following `derived != mean` cannot fail: it is implied.
Moving that assertion onto the two constants instead, `pooled_acs != mean`,
turns it into something with teeth. It guards the test's own premise, because
pooled and averaged coincide whenever every match has the same number of rounds,
and the test is vacuous in that case.

### Asserting a relationship outlasts asserting a value

The same test's strongest line is that the per-round rate is identical whether a
shared match is viewed combined or for one account: numerator and denominator
both double, so the rate holds. Asserting 8000 and 40 pins today's fixture.
Asserting the ratio pins the design, and it is the assertion that fails if anyone
ever counts the rounds of a shared match once while summing both scores.

### An empty test that reports green is worse than a missing test

`tests/test_db.py` was built as scaffolding with eight unwritten bodies. Empty
bodies pass, so the suite would have reported "21 passed" including eight
functions asserting nothing, and CI would have shown a green tick. Marking them
`@pytest.mark.skip(reason="not written yet")` made the run report 13 passed and 8
skipped, which is the true state.

### One fixture, one defect

`tests/fixtures/` holds 13 TOML files, each malformed in exactly one way, with the
broken entry placed second or third so the loader's position counter is proved
rather than assumed. The first attempt had four fixtures not testing what their
names claimed: three were zero-byte files all producing the same
"no entries found" error, and two mixed `[accounts]` with `[[accounts]]` so TOML
refused to parse before the loader ever ran.

Writing them surfaced two real gaps in `config.py`, which now wraps both
`OSError` and `tomllib.TOMLDecodeError` in `ConfigError` with the original chained
via `raise ... from`, so a caller handles one exception type and the traceback
still shows the line tomllib objected to.

### Tests found dead code

`db.match_counts` has no callers anywhere outside its own definition, and it uses
`COUNT(*)` where `headline_stats` uses `COUNT(DISTINCT m.match_id)`. It therefore
carries the exact double-counting bug the rest of the aggregation layer was
changed to avoid. Found while deciding which function the shared-match test should
target.

## SQL and the schema

### `COUNT` returns 0 and `SUM` returns NULL

A filter matching nothing does not produce a row of zeroes:

```
{'matches': 0, 'wins': 0, 'kills': None, 'deaths': None, 'score': None, ...}
```

This is why the no-data guard in `stats.derive` has to run before any arithmetic.
Four of the five ratios fail here with `TypeError: unsupported operand type(s)
for *: 'int' and 'NoneType'`, not `ZeroDivisionError`, so a safe-division helper
would never catch them. Only `win_rate` is a genuine division by zero, and it
happens to be evaluated first, which hid the other four.

### `ON CONFLICT DO NOTHING` keeps the stored row, not the incoming one

Re-ingesting a match whose stats differ silently discards the new values.
Verified: store 99 kills, re-store 1 kill, the row still reads 99. That is correct
here and only here, because a finished match is immutable, so a difference means
the stored copy is right. It would be the wrong resolution for anything still in
progress, where the later read is the accurate one and `DO UPDATE` is needed.

### `PRAGMA foreign_keys` is per connection, not per file

SQLite ignores foreign keys by default and the setting is not stored in the
database file, so a connection opened anywhere else without the pragma accepts a
match pointing at a map that does not exist. Verified both ways: with the pragma
the insert raises, without it the orphan row lands. The test exists specifically to
catch the pragma being dropped from `connect`.

### ISO 8601 text sorts chronologically, so date filters need no parsing

Timestamps are stored as UTC ISO 8601 strings, which sort lexicographically in the
same order as they sort chronologically. A date range filter is therefore a plain
string comparison. Ranges are written half open, because `<= '2026-10-24'` drops
every match played on the 24th, the stored values carrying a time component.

## Design judgement

### Size the fix from the data, not from the imagination

Before deciding how to handle a zero denominator, the live database was queried
for whether it is reachable:

| check | result |
|---|---|
| lowest `deaths` in any performance row | 1 |
| lowest total shots in any performance row | **0** |
| lowest shots in any agent group | 63, over 1 match |

So zero deaths is currently unreachable, needing a flawless match that has not
happened. Zero shots already exists as a row, and single-match agent groups
already exist, so the two only have to coincide once for `report.py` to die with a
traceback on a per-agent split. A real bug with a low arrival rate, which argues
for handling it honestly and not building machinery for it.

### A sentinel that cannot be mistaken for a measurement

An undefined ratio returns `None`, not `0`.

A 20/0 scoreline is the best possible result, and displaying `0.00` K/D for it is
not a degraded answer but the opposite of the truth, with nothing to tell the
reader it is wrong. `float("inf")` is defensible for K/D and meaningless for a
percentage, which would force two rules where one will do.

`f"{None:>6.1f}"` raising `TypeError` is a feature of this choice rather than a
cost: the code fails loudly at the one place that has to change, instead of
printing `None` into a numeric column.

### Guarding at the layer that owns the invariant

The zero-matches guard originally lived in `report.format_row`, which is the
terminal formatter. A guard there protects nothing else, so the dashboard, which
calls `stats.derive` directly, would have crashed on the same input. It now lives
at the top of `derive`, and `format_row`'s remaining check is a presentation
choice rather than a safety one.

The ratio key names are declared once as `stats.RATIOS` so the no-data branch
cannot drift from the normal one, with a test asserting both branches return the
same key set. The declaration alone is not enough, because only the guard
iterates the tuple.

### Proving a refactor changed nothing

`report.py` output was captured before touching `stats.derive` and diffed after.
The real database holds no zero-denominator groups, so every line had to be
byte-identical, and a diff would have meant the arithmetic changed rather than
just the edge cases. The same check was used for the repo-wide `black` pass.

## CI

The GitHub Actions workflow runs `ruff check`, `black --check` and `pytest` on
every push and every pull request, on a pinned Python 3.12 rather than `3.x` so a
new release cannot change the result of a run. `concurrency` with
`cancel-in-progress` cancels a superseded run on the same branch.

It needs no database and no API key. The config tests read fixtures committed to
the repo, and the database tests build their own `:memory:` database from the real
schema, which is also why no test can contaminate another.

One blocker was found before a single test was written: `.gitignore` held
`tests/*.toml`, so every fixture the config tests depend on would have been absent
on the runner.
