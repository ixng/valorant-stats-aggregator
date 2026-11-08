import argparse  # package that reads the command line for me
import sys  # used for sys.exit so the scripts exit code reflects success or failure (0 success, 1 failure)

import config
import db  # to get the match counts and headline stats
import stats  # turns the headline stats into rates such as acs, adr, winrate etc

# I want to make a file i can call as a script in the command line that will formatt and show the stats for each player


# ----------------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------------

# One place for the widths, so the heading and the rows cannot drift apart.
LABEL_WIDTH = 18


def heading(first_column):
    """Return the column headings for a table whose first column has this name."""
    return (
        f"{first_column:{LABEL_WIDTH}} "
        f"{'matches':>7} "
        f"{'wins':>5} "
        f"{'win%':>6} "
        f"{'k/d':>5} "
        f"{'acs':>6} "
        f"{'adr':>6} "
        f"{'hs%':>5}"
    )


def _cell(value, width, places):
    """Format one numeric cell, or a right-aligned dash when the value is None."""
    if value is None:
        return f"{'-':>{width}}"
    return f"{value:>{width}.{places}f}"


def format_row(label, totals):
    """Return one line of output for one row of raw totals.

    Rounding happens here and nowhere else, which is why derive keeps full
    precision.
    """
    if not totals["matches"]:
        return f"{label:{LABEL_WIDTH}} {'no matches':>7}"

    derived = stats.derive(totals)
    return (
        f"{label:{LABEL_WIDTH}} "
        f"{totals['matches']:>7} "
        f"{totals['wins']:>5} "
        f"{_cell(derived['win_rate'], 6, 1)} "
        f"{_cell(derived['kd'], 5, 2)} "
        f"{_cell(derived['acs'], 6, 1)} "
        f"{_cell(derived['adr'], 6, 1)} "
        f"{_cell(derived['hs_percent'], 5, 1)}"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Print the stats already stored by ingest.py. Reads the local "
        "database only and makes no API calls."
    )

    parser.add_argument(
        "--split",
        choices=sorted(db.SPLITS),
        help="break the totals down by either agent or by map",
    )
    parser.add_argument(
        "--account", help='one account as "name#tag"; omit to combine all of them'
    )
    parser.add_argument(
        "--queue",
        default="competitive",
        help="queue to report on (default: competitive)",
    )
    return parser.parse_args(argv)


# ----------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------


def print_headline(conn, accounts, queue_id):
    """Print one row per account, with a combined row first when there is more than one."""
    print(heading("account"))
    if len(accounts) > 1:
        print(format_row("combined", db.headline_stats(conn, None, queue_id)))
    for account in accounts:
        label = f"{account['name']}#{account['tag']}"
        print(format_row(label, db.headline_stats(conn, account["puuid"], queue_id)))


def print_split(conn, split, puuid, queue_id):
    """Print one row per agent or per map, most played first."""
    rows = db.split_stats(conn, split, puuid, queue_id)
    print(heading(split))
    for row in rows:
        print(format_row(row["split_value"], row))

    if split == "agent":
        print()
        print(
            "matches counts games in which that agent was played, "
            "so these rows total more than the headline"
        )


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------


def main(argv=None):
    """Print the stored stats for the configured accounts.

    Returns 0 once something was printed, or 1 if --account named an account
    that is not stored.
    """
    args = parse_args(argv)

    conn = db.connect(config.DB_PATH)
    try:
        accounts = db.all_accounts(conn)
        puuid = None

        if args.account:
            name, separator, tag = args.account.partition("#")
            if not (separator and name and tag):
                print(
                    f'--account must be in "name#tag" form, got {args.account!r}',
                    file=sys.stderr,
                )
                return 1

            accounts = [a for a in accounts if a["name"] == name and a["tag"] == tag]
            if not accounts:
                print(
                    f"{name}#{tag} is not stored in {config.DB_PATH}", file=sys.stderr
                )
                return 1

            puuid = accounts[0]["puuid"]

        if args.split:
            print_split(conn, args.split, puuid, args.queue)
        else:
            print_headline(conn, accounts, args.queue)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
