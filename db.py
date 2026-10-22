import sqlite3


def connect(path):
    """Opens the database at path, creating the file if it does not exist, and returns the connection"""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_accounts_table(conn):
    """Creates an account table only if it doesn't exist already"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS accounts (puuid TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, tag TEXT NOT NULL)"
    )
    conn.commit()

def create_matches_table(conn):
    """Creates a matches table only if it doesn't exist already"""
    conn.execute( 
        "CREATE TABLE IF NOT EXISTS matches (match_id TEXT NOT NULL PRIMARY KEY, map_id TEXT NOT NULL REFERENCES maps(map_id), queue_id TEXT NOT NULL REFERENCES queues(queue_id), started_at TEXT NOT NULL, raw BLOB NOT NULL)"
     )
    conn.commit()

def create_maps_table(conn):
    """Creates a maps table only if it doesn't exist already"""
    conn.execute("CREATE TABLE IF NOT EXISTS maps (map_id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, is_standard_map INTEGER NOT NULL)")
    conn.commit()

def create_agents_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS agents (agent_id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL)")
    conn.commit()

def create_queues_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS queues (queue_id TEXT NOT NULL PRIMARY KEY, mode_type TEXT NOT NULL, name TEXT NOT NULL)")
    conn.commit()

def create_teams_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS teams (match_id TEXT NOT NULL REFERENCES matches(match_id), team_id TEXT NOT NULL, won INTEGER NOT NULL, rounds_won INTEGER NOT NULL, rounds_lost INTEGER NOT NULL, PRIMARY KEY (match_id,team_id))")
    conn.commit()

def create_performances_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS performances"
                 "(match_id TEXT NOT NULL REFERENCES matches(match_id),"
                 "puuid TEXT NOT NULL,team_id TEXT NOT NULL,"
                 "agent_id TEXT NOT NULL REFERENCES agents(agent_id),"
                 "score INTEGER NOT NULL,"
                 "kills INTEGER NOT NULL," 
                 "deaths INTEGER NOT NULL," 
                 "assists INTEGER NOT NULL," 
                 "first_bloods INTEGER NOT NULL,"
                 "headshots INTEGER NOT NULL," 
                 "bodyshots INTEGER NOT NULL," 
                 "legshots INTEGER NOT NULL,"
                 "damage_dealt INTEGER NOT NULL," 
                 "PRIMARY KEY (match_id,puuid),"
                 "FOREIGN KEY (match_id,team_id) REFERENCES teams(match_id,team_id))")
    conn.commit()

def find_puuid(conn, name, tag):
    """Return the PUUID for this name and tag, or None if there's no matching row."""
    cursor = conn.execute(
        "SELECT puuid FROM accounts WHERE name = :name AND tag = :tag",
        {"name": name, "tag": tag},
    )
    row = cursor.fetchone()
    return row[0] if row else None

def prefill_map(conn,map_id,name):
    conn.execute("INSERT INTO maps (map_id,name,is_standard_map) VALUES (:map_id, :name, 1) ON CONFLICT (map_id) DO UPDATE SET is_standard_map = 1", {"map_id" : map_id, "name": name})
def save_account(conn, puuid, name, tag):
    """Saves an new account to the accounts database, however if the puuid already exists it only updates the name and tag on that account"""
    conn.execute(
        "INSERT INTO accounts (puuid, name, tag) VALUES (:puuid, :name, :tag) ON CONFLICT (puuid) DO UPDATE SET name = :name, tag = :tag",
        {"puuid": puuid, "name": name, "tag": tag},
    )
    conn.commit()

def insert_map(conn, row):
    conn.execute("INSERT INTO maps (map_id,name, is_standard_map) "
                "VALUES (:map_id, :name, :is_standard_map) " 
                "ON CONFLICT (map_id) DO NOTHING", 
                row)

def insert_queue(conn, row):
    conn.execute("INSERT INTO queues (queue_id ,mode_type, name) " 
                "VALUES (:queue_id, :mode_type, :name) " 
                "ON CONFLICT (queue_id) DO NOTHING", 
                row)

def insert_match(conn, row):
    """Insert one match. Does nothing if it is already stored, since a finished match never changes."""
    conn.execute("INSERT INTO matches (match_id, map_id, queue_id, started_at, raw) "
                "VALUES (:match_id, :map_id, :queue_id, :started_at, :raw) "
                "ON CONFLICT (match_id) DO NOTHING ",
                row,
    )
def insert_agents(conn, rows):
    conn.executemany("INSERT INTO agents (agent_id, name) "
                     "VALUES (:agent_id, :name) "
                     "ON CONFLICT (agent_id) DO NOTHING ",
                     rows   
                    )
def insert_teams(conn, rows):
    conn.executemany("INSERT INTO teams (match_id, team_id, rounds_won, rounds_lost, won) "
                     "VALUES (:match_id, :team_id, :rounds_won, :rounds_lost, :won) "
                     "ON CONFLICT (match_id,team_id) DO NOTHING",
                     rows   
                    )
def insert_performances(conn, rows):
    """Insert the player rows for one match. Skips any already stored."""
    conn.executemany("INSERT INTO performances (match_id, puuid, team_id, agent_id, score, kills, deaths, assists,first_bloods, headshots, bodyshots, legshots, damage_dealt) " 
                    "VALUES (:match_id, :puuid, :team_id, :agent_id, :score, :kills, :deaths, :assists,:first_bloods, :headshots, :bodyshots, :legshots, :damage_dealt) " 
                    "ON CONFLICT (match_id, puuid) DO NOTHING ",
                    rows)