"""Tests for stats.derive, the one pure function in the project.

derive touches no database and reads its input with ["..."], so a plain dict
is a valid substitute for a sqlite3.Row. That is the whole reason these tests
need no fixture, no connection and no teardown: the function's only input is
its argument.
"""

import pytest

import stats

# Chosen so every ratio is exact and checkable by hand. An expectation worked
# out on paper catches a wrong formula; one copied from a run catches a change.
#
#   win_rate   5 / 10            -> 50.0
#   kd         100 / 50          -> 2.0
#   acs        4000 / 20         -> 200.0
#   adr        3000 / 20         -> 150.0
#   hs_percent 25 / (25+70+5)    -> 25.0   (100 shots in total)
#
# assists and first_bloods are absent on purpose: derive does not read them,
# and if it starts to, these tests fail with a KeyError rather than agree.
BASELINE = {
    "matches": 10,
    "wins": 5,
    "kills": 100,
    "deaths": 50,
    "score": 4000,
    "rounds": 20,
    "damage": 3000,
    "headshots": 25,
    "bodyshots": 70,
    "legshots": 5,
}


def totals(**overrides):
    """BASELINE with some fields replaced, so each test names only what it changes."""
    return {**BASELINE, **overrides}


# ----------------------------------------------------------------------------
# The arithmetic
# ----------------------------------------------------------------------------


def test_derive_computes_every_ratio():
    result = stats.derive(totals())

    assert result == {
        "matches": 10,
        "win_rate": 50.0,
        "kd": 2.0,
        "acs": 200.0,
        "adr": 150.0,
        "hs_percent": 25.0,
    }


def test_derive_keeps_full_precision():
    COMPUTED_STATS = {
        "matches": 493,
        "win_rate": 100 * 255 / 493,
        "kd": 97 / 51,
        "acs": 4001 / 21,
        "adr": 3001 / 21,
        "hs_percent": 100 * 25 / (25 + 70 + 6),
    }
    result = stats.derive(
        totals(
            matches=493,
            wins=255,
            kills=97,
            deaths=51,
            score=4001,
            rounds=21,
            damage=3001,
            headshots=25,
            bodyshots=70,
            legshots=6,
        )
    )
    assert result == COMPUTED_STATS


def test_combined_acs_is_pooled_not_averaged():
    """Why the schema stores score and rounds instead of ACS.

    Two matches, 5000 over 25 rounds and 1800 over 20 rounds. Pooled gives
    6800 / 45 = 151.1, while the mean of the two per-match figures (200 and
    90) gives 145. Only the pooled number answers "what do I average per
    round across this period", which is what the report claims to show.

    Assert derive agrees with the pooled figure and differs from the mean, so
    the test fails if anyone ever reintroduces per-match averaging.
    """
    pooled_acs = 6800 / 45
    mean_of_both_matches_acs = ((5000 / 25) + (1800 / 20)) / 2
    assert pooled_acs != mean_of_both_matches_acs
    derived_pooled_acs = stats.derive(totals(score=6800, rounds=45))["acs"]
    assert derived_pooled_acs == pooled_acs


def test_derive_branches_agree_on_keys():
    assert stats.derive(EMPTY).keys() == stats.derive(totals()).keys()


# ----------------------------------------------------------------------------
# Zero denominators
# ----------------------------------------------------------------------------

# What db.headline_stats returns when the filter matches nothing, which is not
# BASELINE with zeroes in it: COUNT returns 0, but SUM over no rows returns
# NULL. Only win_rate is a real division by zero here. The other four fail on
# None arithmetic with TypeError, which no division guard catches.
EMPTY = {
    "matches": 0,
    "wins": 0,
    "kills": None,
    "deaths": None,
    "score": None,
    "rounds": None,
    "damage": None,
    "headshots": None,
    "bodyshots": None,
    "legshots": None,
}

# A zero denominator in a row that is otherwise real. Both are reachable: the
# live database already holds a zero-shot performance row and already has
# agent groups of one match, so the two only have to coincide once. Each case
# names the ratio it breaks, so the test can assert which one went undefined.
ZERO_CASES = [
    # A flawless match. Unreached so far, the lowest deaths in any stored row
    # being 1, but nothing stops it.
    ("no deaths", "kd", {"deaths": 0}),
    # A player who never fired. An AFK match produces this.
    ("no shots", "hs_percent", {"headshots": 0, "bodyshots": 0, "legshots": 0}),
]


def test_no_matches_gives_no_ratios():
    """The empty filter, with the row shape headline_stats really returns.

    Separate from the parametrized case below because it is a different
    failure: every ratio is undefined at once, so the right output is not a
    row with one gap in it. The guard belongs at the top of derive, before any
    arithmetic touches the Nones.
    """
    result = stats.derive(EMPTY)

    # Not raising is half the assertion: without the guard this call dies on
    # win_rate before the other four are reached.
    assert result["matches"] == 0

    # Against stats.RATIOS, not a list typed here, so it tracks the declaration
    # the guard builds its row from.
    undefined = [key for key, value in result.items() if value is None]
    assert undefined == list(stats.RATIOS)


@pytest.mark.parametrize(
    "affected,overrides",
    [(key, case) for _, key, case in ZERO_CASES],
    ids=[name for name, _, _ in ZERO_CASES],
)
def test_one_undefined_ratio_does_not_poison_the_row(affected, overrides):
    """The affected ratio is None and the other four are still numbers.

    The second half is the assertion with teeth. A single try around the whole
    dict literal would abandon the remaining keys on the first failure, and
    this is the test that would catch it.
    """
    result = stats.derive(totals(**overrides))

    # One comparison covers both halves: the expected ratio is undefined and no
    # other one is. A failure prints both lists, naming the extra keys.
    undefined = [key for key, value in result.items() if value is None]
    assert undefined == [affected]
