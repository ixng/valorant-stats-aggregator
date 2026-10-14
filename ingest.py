import collections
import json,zlib

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
    queue = match_data["queue"]
    blob  = zlib.compress(json.dumps(match, separators=(",",":")).encode())
    row = {
            "match_id" : match_data["match_id"],
            "map_id" : match_data["map"]["id"],
            "queue_id" : "custom" if queue["name"] == "Custom Game" else queue["id"],
            "started_at" : match_data["started_at"],
            "raw" : blob
          }
    
    return row