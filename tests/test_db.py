"""Tests for the schema, the writes and the aggregation queries.

Every test gets its own in-memory database built from the real schema, so
nothing here depends on valstats.db existing and no test can contaminate
another.
"""

import pytest

import db

# One player's stat line. Tests override only the fields they care about,
# so a test about counting matches is not cluttered with headshot numbers.
STATS = {
    "score": 4000,
    "kills": 20,
    "deaths": 20,
    "assists": 5,
    "first_bloods": 2,
    "headshots": 25,
    "bodyshots": 70,
    "legshots": 5,
    "damage_dealt": 3000,
}

ME = "puuid-me"
MATE = "puuid-mate"
STRANGER = "puuid-stranger"


@pytest.fixture
def conn():
    """A fresh empty database per test, with the real schema."""
    connection = db.connect(":memory:")
    db.create_tables(connection)
    db.insert_map(
        connection, {"map_id": "map-ascent", "name": "Ascent", "is_standard_map": 1}
    )
    db.insert_queue(
        connection,
        {"queue_id": "competitive", "mode_type": "standard", "name": "Competitive"},
    )
    db.insert_queue(
        connection, {"queue_id": "deathmatch", "mode_type": "dm", "name": "Deathmatch"}
    )
    db.insert_agents(connection, [{"agent_id": "agent-jett", "name": "Jett"}])
    # ME and MATE are tracked. STRANGER deliberately is not, so a test can
    # prove that untracked players in a stored match contribute nothing.
    db.save_account(connection, ME, "me", "tag")
    db.save_account(connection, MATE, "mate", "tag")
    connection.commit()
    yield connection
    connection.close()


def add_match(
    conn,
    match_id,
    players,
    *,
    queue_id="competitive",
    started_at="2026-09-01T12:00:00Z",
    won=1,
    rounds_won=13,
    rounds_lost=7,
):
    """Store one match with the given players, all on the Blue team.

    players is an iterable of (puuid, stat overrides). Everything a test does
    not name takes the value in STATS.
    """
    db.insert_match(
        conn,
        {
            "match_id": match_id,
            "map_id": "map-ascent",
            "queue_id": queue_id,
            "started_at": started_at,
        },
    )
    db.insert_teams(
        conn,
        [
            {
                "match_id": match_id,
                "team_id": "Blue",
                "won": won,
                "rounds_won": rounds_won,
                "rounds_lost": rounds_lost,
            }
        ],
    )
    db.insert_performances(
        conn,
        [
            {
                "match_id": match_id,
                "puuid": puuid,
                "team_id": "Blue",
                "agent_id": "agent-jett",
                **STATS,
                **overrides,
            }
            for puuid, overrides in players
        ],
    )
    conn.commit()


# ----------------------------------------------------------------------------
# The per-match counting rule
# ----------------------------------------------------------------------------


@pytest.mark.skip(reason="not written yet")
def test_shared_match_counts_once_for_the_combined_view(conn):
    """Two tracked accounts in one match is one match, not two.

    This is the bug the real database had: 615 performance rows across 493
    matches, because the accounts queue together.
    """


@pytest.mark.skip(reason="not written yet")
def test_shared_match_sums_both_appearances(conn):
    """The two grains in one row.

    matches counts distinct ids, but kills, score and rounds stay per
    appearance, so ACS over a shared match uses both players' scores and
    both players' rounds.
    """


@pytest.mark.skip(reason="not written yet")
def test_untracked_players_are_excluded(conn):
    """A performance row whose puuid is not in accounts contributes nothing."""


# ----------------------------------------------------------------------------
# Filtering and idempotency
# ----------------------------------------------------------------------------


@pytest.mark.skip(reason="not written yet")
def test_other_queues_are_excluded(conn):
    """A deathmatch has no rounds and would make ACS meaningless."""


@pytest.mark.skip(reason="not written yet")
def test_storing_a_match_twice_changes_nothing(conn):
    """Ingestion re-fetches matches it has already seen on every run."""


# ----------------------------------------------------------------------------
# Edge cases and the split allowlist
# ----------------------------------------------------------------------------


@pytest.mark.skip(reason="not written yet")
def test_empty_database_returns_zero_matches(conn):
    """What report.format_row's guard is defending against."""


@pytest.mark.skip(reason="not written yet")
def test_split_stats_rejects_an_unknown_split(conn):
    """The allowlist. A caller's split name is only ever a dict key."""


@pytest.mark.skip(reason="not written yet")
def test_foreign_keys_are_enforced(conn):
    """connect() sets PRAGMA foreign_keys = ON, which is per connection."""
