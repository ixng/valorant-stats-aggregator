# Named once so the no-data branch below cannot drift from the normal one.
RATIOS = ("win_rate", "kd", "acs", "adr", "hs_percent")


def _ratio(numerator, denominator):
    """Return the division, or None when the denominator is zero."""
    if not denominator:
        return None
    return numerator / denominator


def derive(totals):
    """Turn the raw sums into the numbers a person reads."""
    if not totals["matches"]:
        return {"matches": totals["matches"], **{key: None for key in RATIOS}}

    shots = totals["headshots"] + totals["bodyshots"] + totals["legshots"]

    return {
        "matches": totals["matches"],
        "win_rate": _ratio(100 * totals["wins"], totals["matches"]),
        "kd": _ratio(totals["kills"], totals["deaths"]),
        "acs": _ratio(totals["score"], totals["rounds"]),
        "adr": _ratio(totals["damage"], totals["rounds"]),
        "hs_percent": _ratio(100 * totals["headshots"], shots),
    }
