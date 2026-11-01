-- The published aggregates. One row per (account, split).
--
-- Raw sums, not ratios, for the same reason the local database stores them that
-- way: a stored percentage cannot be re-aggregated, and SQLite integer division
-- would have ruined it anyway. The Worker divides on the way out.
--
-- No per-match rows and no raw responses: the nine other players in each match
-- are not published.
CREATE TABLE IF NOT EXISTS stats (
  account      TEXT NOT NULL,  -- "combined", or "name#tag"
  split_kind   TEXT NOT NULL,  -- "overall", "agent", "map"
  split_value  TEXT NOT NULL,  -- "" for overall, else the agent or map name
  matches      INTEGER NOT NULL,
  wins         INTEGER NOT NULL,
  kills        INTEGER NOT NULL,
  deaths       INTEGER NOT NULL,
  assists      INTEGER NOT NULL,
  score        INTEGER NOT NULL,
  damage       INTEGER NOT NULL,
  headshots    INTEGER NOT NULL,
  bodyshots    INTEGER NOT NULL,
  legshots     INTEGER NOT NULL,
  first_bloods INTEGER NOT NULL,
  rounds       INTEGER NOT NULL,
  PRIMARY KEY (account, split_kind, split_value)
);
