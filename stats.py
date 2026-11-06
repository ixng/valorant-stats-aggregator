# Named once so the no-data branch below cannot drift from the normal one.
RATIOS = ("win_rate", "kd", "acs", "adr", "hs_percent")


def _ratio(numerator, denominator):
    """Return the division, or None when the denominator is zero.

    None rather than 0, because an undefined ratio is not a low one. A match
    with no deaths is the best possible result, so a 0.00 K/D would state the
    opposite with nothing to mark it wrong. Callers format None as a dash.
    """
    if not denominator:
        return None
    return numerator / denominator


def derive(totals):
    """Turn the raw sums into the numbers a person reads.

    Takes a row from db.headline_stats. Returns a dict. Touches no database,
    so it can be tested with a hand-written dict of totals.

    A filter matching nothing gives matches = 0 and NULL for every sum, so
    every ratio is undefined at once and None is returned for all of them.
    This has to be checked before any arithmetic runs: the sums arrive as None
    rather than 0, and None / None is a TypeError, which no division guard
    would catch.
    """
    if not totals["matches"]:
        return {"matches": totals["matches"], **{key: None for key in RATIOS}}

    shots = totals["headshots"] + totals["bodyshots"] + totals["legshots"]

    # The 100 multiplier goes inside the numerator. Outside the call it would
    # raise TypeError on a None return, and float multiplication is not
    # associative, so 100 * (wins / matches) is a different number.
    return {
        "matches": totals["matches"],
        "win_rate": _ratio(100 * totals["wins"], totals["matches"]),
        "kd": _ratio(totals["kills"], totals["deaths"]),
        "acs": _ratio(totals["score"], totals["rounds"]),
        "adr": _ratio(totals["damage"], totals["rounds"]),
        "hs_percent": _ratio(100 * totals["headshots"], shots),
    }
