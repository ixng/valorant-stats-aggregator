"""Tests for stats.derive, the one pure function in the project.

derive touches no database and reads its input with ["..."], so a plain dict
is a valid substitute for a sqlite3.Row. That is the whole reason these tests
need no fixture, no connection and no teardown: the function's only input is
its argument.
"""

import pytest

import stats

# Chosen so every ratio is exact and checkable by hand.
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


ZERO_CASES = [
    # A flawless match with deaths = 0
    ("no deaths", "kd", {"deaths": 0}),
    # A player who never fired. An AFK match produces this.
    ("no shots", "hs_percent", {"headshots": 0, "bodyshots": 0, "legshots": 0}),
]


def test_no_matches_gives_no_ratios():

    result = stats.derive(EMPTY)

    assert result["matches"] == 0

    # Tracks the declaration the guard builds its row from.
    undefined = [key for key, value in result.items() if value is None]
    assert undefined == list(stats.RATIOS)


@pytest.mark.parametrize(
    "affected,overrides",
    [(key, case) for _, key, case in ZERO_CASES],
    ids=[name for name, _, _ in ZERO_CASES],
)
def test_one_undefined_ratio_does_not_poison_the_row(affected, overrides):
    """The affected ratio is None and the other four are still numbers."""
    result = stats.derive(totals(**overrides))

    # One comparison covers both halves: the expected ratio is undefined and no
    # other one is. A failure prints both lists, naming the extra keys.
    undefined = [key for key, value in result.items() if value is None]
    assert undefined == [affected]
