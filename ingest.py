import collections
import json
import zlib
import db
import pathlib
import sys
DB_PATH = "valstats.db"


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


