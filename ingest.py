import argparse
import collections
import json
import pathlib
import sys
import zlib

import api
import config
import db
import resolve

DB_PATH = "valstats.db"
CONFIG_PATH = "accounts.toml"
MAX_CONSECUTIVE_PAGE_FAILURES = 3
MAP_PATH = "maps.toml"
MAX_PAGES = 50
SIZE = 10


# ----------------------------------------------------------------------------
# Values the API does not provide
# ----------------------------------------------------------------------------


def first_bloods(match):
    """Groups the kills by round then, takes the one with the lowest time_in_round_in_ms in each round
    and credit killer.puuid. Returns a Counter object mapping puuid to the players first blood counts.
    """

    kill_events = match["kills"]
    kills_in_each_round = collections.defaultdict(list)
    first_bloods_in_each_round = []

    for kill in kill_events:
        kills_in_each_round[kill["round"]].append(
            (kill["killer"]["puuid"], kill["time_in_round_in_ms"])
        )

    for kills in kills_in_each_round.values():
        first_bloods_in_each_round.append(kills[0][0])

    counter = collections.Counter(first_bloods_in_each_round)
    return counter


def queue_id(match_data):
    queue = match_data["queue"]
    return "custom" if queue["name"] == "Custom Game" else queue["id"]


# ----------------------------------------------------------------------------
# One match into rows, one function per table
# ----------------------------------------------------------------------------


def map_row(match):
    meta_data = match["metadata"]
    map_data = meta_data["map"]
    return {"map_id": map_data["id"], "name": map_data["name"], "is_standard_map": 0}


def queue_row(match):
    meta_data = match["metadata"]
    queue_data = meta_data["queue"]
    name = queue_data["name"]
    mode_type = queue_data["mode_type"]
    queue = {
        "queue_id": queue_id(meta_data),
        "name": name if name is not None else mode_type,
        "mode_type": mode_type,
    }
    return queue


def agent_rows(match):
    players_data = match["players"]
    agents = []

    for player in players_data:
        agent_data = player["agent"]
        agent = {"agent_id": agent_data["id"], "name": agent_data["name"]}
        if agent not in agents:
            agents.append(agent)

    return agents


def match_row(match):
    match_data = match["metadata"]
    row = {
        "match_id": match_data["match_id"],
        "map_id": match_data["map"]["id"],
        "queue_id": queue_id(match_data),
        "started_at": match_data["started_at"],
    }

    return row


def archive_row(match):
    match_data = match["metadata"]
    blob = zlib.compress(json.dumps(match, separators=(",", ":")).encode())
    row = {
        "match_id": match_data["match_id"],
        "raw": blob,
    }
    return row


def team_rows(match):

    match_id = match["metadata"]["match_id"]
    teams = match["teams"]
    list_of_teams = []

    for team in teams:
        rounds = team["rounds"]
        row = {
            "match_id": match_id,
            "team_id": team["team_id"],
            "rounds_won": rounds["won"],
            "rounds_lost": rounds["lost"],
            "won": int(team["won"]),
        }
        list_of_teams.append(row)

    return list_of_teams


def performance_rows(match):

    match_id = match["metadata"]["match_id"]
    players = match["players"]
    list_of_players = []
    all_first_bloods = first_bloods(match)

    for player in players:
        puuid = player["puuid"]
        stats = player["stats"]
        first_blood_count = all_first_bloods.get(puuid, 0)
        row = {
            "match_id": match_id,
            "puuid": puuid,
            "team_id": player["team_id"],
            "agent_id": player["agent"]["id"],
            "score": stats["score"],
            "kills": stats["kills"],
            "deaths": stats["deaths"],
            "assists": stats["assists"],
            "first_bloods": first_blood_count,
            "headshots": stats["headshots"],
            "bodyshots": stats["bodyshots"],
            "legshots": stats["legshots"],
            "damage_dealt": stats["damage"]["dealt"],
        }
        list_of_players.append(row)

    return list_of_players


# ----------------------------------------------------------------------------
# Writing a whole match
# ----------------------------------------------------------------------------


def save_match(conn, match):
    with conn:
        db.insert_map(conn, map_row(match))
        db.insert_queue(conn, queue_row(match))
        db.insert_agents(conn, agent_rows(match))
        db.insert_match(conn, match_row(match))
        db.insert_match_archive(conn, archive_row(match))
        db.insert_teams(conn, team_rows(match))
        db.insert_performances(conn, performance_rows(match))


# ----------------------------------------------------------------------------
# Loading the saved archive pages
# ----------------------------------------------------------------------------


def load_archive(conn, directory):
    """Load every match in the saved archive pages into the database.

    Reads the raw API responses saved under `directory` and passes each match
    through save_match. Makes no API calls: this is the only source for matches
    that have since aged out of the window the API serves.

    Returns (files_read, matches_saved).
    """
    files_read = 0
    matches_saved = 0

    for path in sorted(pathlib.Path(directory).glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"skipped {path.name}: not valid JSON ({e})", file=sys.stderr)
            continue

        files_read += 1
        for match in doc.get("data") or []:
            save_match(conn, match)
            matches_saved += 1

    return files_read, matches_saved


# ----------------------------------------------------------------------------
# Fetching from the API
# ----------------------------------------------------------------------------


def recover_page(conn, puuid, api_key, start, label):
    """Refetch one page's offsets one at a time, after the page as a whole failed.

    A page fails when a single match in it cannot be served, so fetching the offsets
    individually saves the others. The bad match cannot be recorded and skipped by id,
    because the request that would reveal its match_id is the one that fails, and its
    offset moves as new matches are played, so this runs afresh each time.

    Returns (saved, skipped).
    """
    saved = 0
    skipped = 0

    for offset in range(start, start + SIZE):
        try:
            page = api.fetch_matches(puuid, api_key, offset, 1)
        except api.RequestFailed:
            print(f"{label}: no match recoverable at offset {offset}", file=sys.stderr)
            skipped += 1
            continue

        if not page:
            break

        save_match(conn, page[0])
        saved += 1

    return saved, skipped


def ingest_account(conn, puuid, api_key, label, full=False):
    """Fetch and store this account's matches that are not already stored.

    Pages from newest to oldest until a page comes back empty or short, up to
    MAX_PAGES as a backstop. Normally it also stops at the first page whose matches
    are all already stored, since matches arrive newest first and everything behind
    such a page is older. Passing full keeps going to the end of the window instead,
    which is how a gap left by an interrupted run gets healed.

    A page that fails is recovered match by match rather than abandoning the account,
    since everything older than it would otherwise be unreachable. The account is given
    up on after MAX_CONSECUTIVE_PAGE_FAILURES failures in a row, which distinguishes one
    unservable match from the API being down.

    Returns (saved, skipped). AccountNotFound and InvalidApiKey propagate, since neither
    improves on the next page.
    """
    saved = 0
    skipped = 0
    consecutive_failures = 0
    for page_num in range(MAX_PAGES):
        start = page_num * SIZE

        try:
            page = api.fetch_matches(puuid, api_key, start, SIZE)
        except api.RequestFailed as e:
            print(
                f"{label}: page at offset {start} failed ({e}); "
                "recovering it one match at a time",
                file=sys.stderr,
            )
            page_saved, page_skipped = recover_page(conn, puuid, api_key, start, label)
            saved += page_saved
            skipped += page_skipped

            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_PAGE_FAILURES:
                print(
                    f"{label}: giving up after {consecutive_failures} page failures in a row",
                    file=sys.stderr,
                )
                break
            continue

        consecutive_failures = 0
        if not page:
            break

        # Asked before saving: afterwards every match on the page is stored,
        # so the answer would always be "stop".
        page_ids = [match["metadata"]["match_id"] for match in page]
        known = db.known_match_ids(conn, page_ids)

        for match in page:
            save_match(conn, match)
            saved += 1

        if len(known) == len(page) and not full:
            pages = page_num + 1
            print(f"{label}: caught up after {pages} page{'s' if pages > 1 else ''}")
            break

        if len(page) < SIZE:
            break
    else:
        print(f"{label}: stopped at the {MAX_PAGES} page cap", file=sys.stderr)

    return saved, skipped


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------


def parse_args(argv=None):
    """Read the command line. Returns the parsed arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch Valorant matches for every configured account and store them."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="sweep each account's whole window instead of stopping at matches already stored",
    )
    return parser.parse_args(argv)


def main(argv=None):
    """Resolve and ingest every account in the config.

    Reports fetched, new and unavailable counts per account, keeps going when one
    account fails, and returns 1 if any did so the caller can exit non-zero.
    """
    args = parse_args(argv)

    api_key = config.load_api_key()
    accounts = config.load_accounts(CONFIG_PATH)
    conn = db.connect(DB_PATH)
    failures = 0
    total_matches = 0
    try:
        db.create_tables(conn)
        db.prefill_maps(conn, config.load_maps(MAP_PATH))

        for name, tag in accounts:
            label = f"{name}#{tag}"
            try:
                puuid = resolve.resolve_account(conn, name, tag, api_key)
                before = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                fetched, skipped = ingest_account(
                    conn, puuid, api_key, label, full=args.full
                )
                after = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                summary = f"{label}: {fetched} matches fetched, {after - before} new"
                if skipped:
                    summary += f", {skipped} unavailable"
                print(summary)
                total_matches += after - before

            except (api.AccountNotFound, api.RequestFailed) as e:
                print(f" ERROR: {name}#{tag}: {e}", file=sys.stderr)
                failures += 1
            except api.InvalidApiKey as e:
                print(f" ERROR: {e}", file=sys.stderr)
                sys.exit(1)

        mode = "full sweep" if args.full else "stopping at stored matches"
        print(f"{total_matches} new matches across {len(accounts)} accounts ({mode})")

    finally:
        conn.close()

    if failures > 0:
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
