import collections

def first_bloods(match):
    """Groups the kills by round then, takes the one with the lowest time_in_round_in_ms in each round
    and credit credit killer.puuid. Returns a dict mapping puuid to first blood counts."""

    kill_events = match["kills"]
    kills_in_each_round = collections.defaultdict(list)

    for kill in kill_events:
        
    ...