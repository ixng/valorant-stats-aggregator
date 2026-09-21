import sqlite3


def connect(path):
    """Opens the database at path, creating the file if it does not exist, and returns the connection"""
    conn = sqlite3.connect(path)
    return conn


def create_accounts_table(conn):
    """Creates an account table only if it doesn't exist already"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS accounts (puuid TEXT PRIMARY KEY, name TEXT, tag TEXT)"
    )
    conn.commit()


def find_puuid(conn, name, tag):
    """Return the PUUID for this name and tag, or None if there's no matching row."""
    cursor = conn.execute(
        "SELECT puuid FROM accounts WHERE name = :name AND tag = :tag",
        {"name": name, "tag": tag},
    )
    row = cursor.fetchone()
    return row[0] if row else None


def save_account(conn, puuid, name, tag):
    """Saves an new account to the accounts database, however if the puuid already exists it only updates the name and tag on that account"""
    conn.execute(
        "INSERT INTO accounts (puuid, name, tag) VALUES (:puuid, :name, :tag) ON CONFLICT (puuid) DO UPDATE SET name = :name, tag = :tag",
        {"puuid": puuid, "name": name, "tag": tag},
    )
    conn.commit()
