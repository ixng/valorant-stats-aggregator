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
MAP_PATH = "maps.toml"
MAX_PAGES = 50
SIZE = 10
def first_bloods(match):
    """Groups the kills by round then, takes the one with the lowest time_in_round_in_ms in each round
    and credit killer.puuid. Returns a Counter object mapping puuid to the players first blood counts."""

    kill_events = match["kills"]
    kills_in_each_round = collections.defaultdict(list)
    first_bloods_in_each_round = []

    for kill in kill_events:
        kills_in_each_round[kill["round"]].append((kill["killer"]["puuid"],kill["time_in_round_in_ms"]))
    
    for kills in kills_in_each_round.values():
        first_bloods_in_each_round.append(kills[0][0])
    
    counter = collections.Counter(first_bloods_in_each_round)
    return counter
    
def performance_rows(match):

    match_id = match["metadata"]["match_id"]
    players = match["players"]
    list_of_players = []
    all_first_bloods = first_bloods(match)

    for player in players:
        puuid = player["puuid"]
        stats = player["stats"]
        first_blood_count = all_first_bloods.get(puuid,0)
        row = {
            "match_id" : match_id,
            "puuid" : puuid,
            "team_id" : player["team_id"],
            "agent_id" : player["agent"]["id"],
            "score" : stats["score"],
            "kills" : stats["kills"],
            "deaths" : stats["deaths"],
            "assists" : stats["assists"],
            "first_bloods" : first_blood_count,
            "headshots" : stats["headshots"],
            "bodyshots" : stats["bodyshots"],
            "legshots" : stats["legshots"],
            "damage_dealt" : stats["damage"]["dealt"]
        }
        list_of_players.append(row)

    return list_of_players

def team_rows(match):

    match_id = match["metadata"]["match_id"]
    teams = match["teams"]
    list_of_teams = []

    for team in teams:
        rounds = team["rounds"]
        row = {
            "match_id" : match_id,
            "team_id" : team["team_id"],
            "rounds_won" : rounds["won"],
            "rounds_lost" : rounds["lost"],
            "won" : int(team["won"]) 
        }
        list_of_teams.append(row)
    
    return list_of_teams

def match_row(match):
    match_data = match["metadata"]
    blob  = zlib.compress(json.dumps(match, separators=(",",":")).encode())
    row = {
            "match_id" : match_data["match_id"],
            "map_id" : match_data["map"]["id"],
            "queue_id" : queue_id(match_data),
            "started_at" : match_data["started_at"],
            "raw" : blob
          }
    
    return row

def queue_id(match_data):
    queue = match_data["queue"]
    return "custom" if queue["name"] == "Custom Game" else queue["id"]

def map_row(match):   
    meta_data = match["metadata"]
    map_data = meta_data["map"]
    return {"map_id" : map_data["id"], "name" : map_data["name"], "is_standard_map": 0 }

def agent_rows(match):   
    players_data = match["players"]
    agents = []
    
    for player in players_data:
        agent_data = player["agent"]
        agent = {
            "agent_id" : agent_data["id"],
            "name" : agent_data["name"]
        }
        if agent not in agents:
            agents.append(agent)
    
    return agents
    
def queue_row(match):
    meta_data = match["metadata"]
    queue_data = meta_data["queue"]
    name = queue_data["name"]
    mode_type = queue_data["mode_type"]
    queue = {
        "queue_id" : queue_id(meta_data),
        "name" : name if name is not None else mode_type,
        "mode_type" : mode_type
    }
    return queue

def save_match(conn, match):
    with conn:
        db.insert_map(conn,map_row(match))
        db.insert_queue(conn,queue_row(match))
        db.insert_agents(conn,agent_rows(match))
        db.insert_match(conn,match_row(match))
        db.insert_teams(conn,team_rows(match))
        db.insert_performances(conn,performance_rows(match))

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

def ingest_account(conn, puuid, api_key, label):
    """Fetch and store every match the API still holds for one account.

    Pages from newest to oldest until a page comes back empty or short, up to
    MAX_PAGES as a backstop. Returns the number of matches saved. Raises the
    api errors unchanged, so the caller decides whether to skip or stop.
    """
    saved = 0

    for page_num in range(MAX_PAGES):
        page = api.fetch_matches(puuid, api_key, page_num * SIZE, SIZE)

        if not page:
            break

        for match in page:
            save_match(conn, match)
            saved += 1

        if len(page) < SIZE:
            break
    else:
        print(f"{label}: stopped at the {MAX_PAGES} page cap", file=sys.stderr)

    return saved
def main():
    
    api_key = config.load_api_key()
    accounts = config.load_accounts(CONFIG_PATH)
    conn = db.connect(DB_PATH)
    failures = 0
    total_matches = 0
    try:
        db.create_tables(conn)
        db.prefill_maps(conn,config.load_maps(MAP_PATH))

        for name, tag in accounts:
            label = f"{name}#{tag}"
            try:
                puuid = resolve.resolve_account(conn, name, tag, api_key)
                before = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                fetched = ingest_account(conn, puuid, api_key, label)
                after = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                print(f"{label}: {fetched} matches fetched, {after - before} new")
                total_matches += after - before  

            except (api.AccountNotFound, api.RequestFailed) as e:
                print(f" ERROR: {name}#{tag}: {e}", file=sys.stderr)
                failures += 1
            except api.InvalidApiKey as e:
                print(f" ERROR: {e}", file=sys.stderr)
                sys.exit(1)

        print(f"{total_matches} new matches across {len(accounts)} accounts")

    finally:
        conn.close()
    

    if failures > 0:
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())