"""Write the stored aggregates out as SQL for Cloudflare D1.

Reads the local database through the same functions report.py uses, and writes
INSERT statements to worker/stats.sql. Makes no network calls: pushing the file
is a separate step, so a bad export never reaches the published API.

Only the tracked accounts' own aggregates are written. No per-match rows and no
raw responses leave the machine.
"""

import pathlib
import sys

import db

DB_PATH = "valstats.db"
OUT_PATH = pathlib.Path("worker/stats.sql")
QUEUE_ID = "competitive"

COLUMNS = (
    "account",
    "split_kind",
    "split_value",
    "matches",
    "wins",
    "kills",
    "deaths",
    "assists",
    "score",
    "damage",
    "headshots",
    "bodyshots",
    "legshots",
    "first_bloods",
    "rounds",
)

# Everything except the three primary key columns is replaced on conflict, so a
# re-export overwrites yesterday's totals rather than being ignored.
UPDATES = ", ".join(f"{c} = excluded.{c}" for c in COLUMNS[3:])


def quote(value):
    """Return value as a SQL literal. Doubles single quotes in text."""
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def row_values(account, split_kind, split_value, totals):
    """Return one row of values in COLUMNS order, or None if there is no data."""
    if not totals["matches"]:
        return None
    head = (account, split_kind, split_value)
    return head + tuple(totals[c] for c in COLUMNS[3:])


def collect(conn):
    """Return every row to publish: overall and both splits, combined and per account."""
    targets = [("combined", None)]
    for account in db.all_accounts(conn):
        targets.append((f"{account['name']}#{account['tag']}", account["puuid"]))

    rows = []
    for label, puuid in targets:
        overall = db.headline_stats(conn, puuid, QUEUE_ID)
        row = row_values(label, "overall", "", overall)
        if row is not None:
            rows.append(row)

        for split in sorted(db.SPLITS):
            for totals in db.split_stats(conn, split, puuid, QUEUE_ID):
                row = row_values(label, split, totals["split_value"], totals)
                if row is not None:
                    rows.append(row)

    return rows


def statements(rows):
    """Yield one INSERT per row."""
    columns = ", ".join(COLUMNS)
    for row in rows:
        values = ", ".join(quote(value) for value in row)
        yield (
            f"INSERT INTO stats ({columns}) VALUES ({values}) "
            f"ON CONFLICT (account, split_kind, split_value) DO UPDATE SET {UPDATES};"
        )


def main(argv=None):
    conn = db.connect(DB_PATH)
    try:
        rows = collect(conn)
    finally:
        conn.close()

    if not rows:
        print("nothing to export", file=sys.stderr)
        return 1

    OUT_PATH.write_text("\n".join(statements(rows)) + "\n")
    print(f"wrote {len(rows)} rows to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
