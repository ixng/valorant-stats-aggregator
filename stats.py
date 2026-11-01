def derive(totals):
    """Turn the raw sums into the numbers a person reads.

    Takes a row from db.headline_stats. Returns a dict. Touches no database,
    so it can be tested with a hand-written dict of totals.
    """
    return {
        "matches": totals["matches"],
        "win_rate": 100 * totals["wins"] / totals["matches"],
        "kd": totals["kills"] / totals["deaths"],
        "acs": totals["score"] / totals["rounds"],
        "adr": totals["damage"] / totals["rounds"],
        "hs_percent": 100
        * totals["headshots"]
        / (totals["headshots"] + totals["bodyshots"] + totals["legshots"]),
    }
