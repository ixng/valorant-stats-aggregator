"""Tests for the schema, the writes and the aggregation queries.

Every test gets its own in-memory database built from the real schema, so
nothing here depends on valstats.db existing and no test can contaminate
another.
"""

import re
import sqlite3

import pytest

import db

# One player's stat line. Tests override only the fields they care about.
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


def test_shared_match_counts_once_for_the_combined_view(conn):
    """Two tracked accounts in one match is one match, not two.

    This is the bug the real database had: 615 performance rows across 493
    matches, because the accounts queue together.
    """
    add_match(conn, "match-shared", [(ME, {}), (MATE, {})])

    totals = db.headline_stats(conn)

    assert totals["kills"] == 40
    assert totals["matches"] == 1


def test_shared_match_sums_both_appearances(conn):
    """The two grains in one row.

    matches counts distinct ids, but kills, score and rounds stay per
    appearance, so ACS over a shared match uses both players' scores and
    both players' rounds.
    """
    add_match(conn, "match-shared", [(ME, {}), (MATE, {})])

    combined = db.headline_stats(conn)
    mine = db.headline_stats(conn, puuid=ME)

    # Both rows join to the same single teams row, so its 20 rounds are
    # counted once per appearance: 4000 score and 20 rounds each.
    assert combined["score"] == 8000
    assert combined["rounds"] == 40
    assert mine["score"] == 4000
    assert mine["rounds"] == 20

    # Numerator and denominator both doubled, so the rate is the same either
    # way. Counting the rounds once while summing both scores gives 400.
    assert combined["score"] / combined["rounds"] == mine["score"] / mine["rounds"]


def test_untracked_players_are_excluded(conn):
    """A performance row whose puuid is not in accounts contributes nothing."""
    # STRANGER stands for the nine other players a stored match really holds.
    # No save_account call, so the JOIN on accounts drops the row.
    add_match(conn, "match-shared", [(ME, {}), (MATE, {}), (STRANGER, {})])

    stored_rows = conn.execute("SELECT COUNT(*) FROM performances").fetchone()[0]
    totals = db.headline_stats(conn)

    # Three rows in, two out. The stored count separates "the join excluded
    # them" from "the insert never happened".
    assert stored_rows == 3
    assert totals["kills"] == 40


# ----------------------------------------------------------------------------
# Filtering and idempotency
# ----------------------------------------------------------------------------


def test_other_queues_are_excluded(conn):
    """A deathmatch has no rounds and would make ACS meaningless."""
    add_match(conn, "match-comp", [(ME, {})])
    add_match(conn, "match-dm", [(ME, {})], queue_id="deathmatch")

    competitive = db.headline_stats(conn)
    deathmatch = db.headline_stats(conn, queue_id="deathmatch")

    # Querying the deathmatch explicitly proves it was stored, so a failed
    # insert cannot masquerade as a working filter.
    assert competitive["matches"] == 1
    assert competitive["kills"] == 20
    assert deathmatch["matches"] == 1


def test_storing_a_match_twice_changes_nothing(conn):
    """Ingestion re-fetches matches it has already seen on every run."""
    add_match(conn, "match-twice", [(ME, {})])
    first = dict(db.headline_stats(conn))

    add_match(conn, "match-twice", [(ME, {})])
    second = dict(db.headline_stats(conn))

    # Comparing whole rows catches a double count in any column, not just the
    # ones other tests name.
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM performances").fetchone()[0] == 1


# ----------------------------------------------------------------------------
# Edge cases and the split allowlist
# ----------------------------------------------------------------------------


def test_empty_database_returns_zero_matches(conn):
    """What report.format_row's guard is defending against."""
    stats_row = db.headline_stats(conn)
    total_matches = stats_row["matches"]
    total_kills = stats_row["kills"]
    assert total_kills is None
    assert total_matches == 0


def test_split_stats_rejects_an_unknown_split(conn):
    """The allowlist. A caller's split name is only ever a dict key."""
    with pytest.raises(
        ValueError,
        match=re.escape("unknown split 'agents', expected one of ['agent', 'map']"),
    ):
        db.split_stats(conn, "agents")


def test_foreign_keys_are_enforced(conn):
    """connect() sets PRAGMA foreign_keys = ON, which is per connection.

    SQLite ignores foreign keys by default, and the setting does not live in
    the file, so a connection opened anywhere else in the codebase without the
    pragma would accept a match pointing at a map that does not exist. This
    test exists to catch that pragma being dropped from connect().
    """
    orphan = {
        "match_id": "match-orphan",
        "map_id": "map-haven",
        "queue_id": "competitive",
        "started_at": "2026-09-01T12:00:00Z",
    }

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        db.insert_match(conn, orphan)
