// A read-only API over the aggregates pushed from the local pipeline.
//
// This Worker holds no credentials and calls no third-party service. It reads
// the `stats` table in D1, which export_d1.py fills with derived totals only:
// no per-match rows and no other players' data.
//
// Ratios are computed here rather than stored, for the same reason the local
// database stores raw sums: a stored percentage cannot be re-aggregated.

interface D1Result<T> {
  results: T[];
}

interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  all<T>(): Promise<D1Result<T>>;
}

interface D1Database {
  prepare(query: string): D1PreparedStatement;
}

interface Env {
  DB: D1Database;
}

interface Totals {
  account: string;
  split_kind: string;
  split_value: string;
  matches: number;
  wins: number;
  kills: number;
  deaths: number;
  assists: number;
  score: number;
  damage: number;
  headshots: number;
  bodyshots: number;
  legshots: number;
  first_bloods: number;
  rounds: number;
}

const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "public, max-age=300",
  // Public read-only data, so any page may fetch it. This is what lets a
  // dashboard on another origin call the API from the browser.
  "access-control-allow-origin": "*",
};

// Kept identical to stats.derive in the Python. Full precision: rounding is the
// caller's job, the same decision the rest of the project makes.
function derive(totals: Totals) {
  const shots = totals.headshots + totals.bodyshots + totals.legshots;
  return {
    split: totals.split_value || null,
    matches: totals.matches,
    wins: totals.wins,
    win_rate: (100 * totals.wins) / totals.matches,
    kd: totals.kills / totals.deaths,
    acs: totals.score / totals.rounds,
    adr: totals.damage / totals.rounds,
    hs_percent: shots === 0 ? null : (100 * totals.headshots) / shots,
    kills: totals.kills,
    deaths: totals.deaths,
    assists: totals.assists,
    first_bloods: totals.first_bloods,
    rounds: totals.rounds,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body, null, 2), { status, headers: HEADERS });
}

async function rows(env: Env, account: string, splitKind: string): Promise<Totals[]> {
  const result = await env.DB.prepare(
    "SELECT * FROM stats WHERE account = ? AND split_kind = ? ORDER BY matches DESC",
  )
    .bind(account, splitKind)
    .all<Totals>();
  return result.results;
}

async function index(env: Env): Promise<Response> {
  const result = await env.DB.prepare(
    "SELECT account, COUNT(*) AS rows FROM stats GROUP BY account ORDER BY account",
  ).all<{ account: string; rows: number }>();

  return json({
    about: "Aggregated Valorant competitive stats, pushed from a local ingestion pipeline.",
    accounts: result.results.map((row) => ({
      account: row.account,
      overall: `/stats/${encodeURIComponent(row.account)}`,
      agents: `/stats/${encodeURIComponent(row.account)}/agent`,
      maps: `/stats/${encodeURIComponent(row.account)}/map`,
    })),
    notes: {
      queue: "competitive only",
      matches:
        "distinct matches in the overall view; in the agent view, matches in which that agent was played",
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    const parts = pathname.split("/").filter((part) => part.length > 0);

    if (parts.length === 0) {
      return index(env);
    }

    if (parts[0] !== "stats" || parts.length > 3) {
      return json({ error: "not found", try: "/" }, 404);
    }

    const account = decodeURIComponent(parts[1] ?? "");
    const splitKind = parts.length === 3 ? decodeURIComponent(parts[2]) : "overall";

    if (!["overall", "agent", "map"].includes(splitKind)) {
      return json({ error: `unknown split ${splitKind}`, expected: ["agent", "map"] }, 404);
    }

    const found = await rows(env, account, splitKind);
    if (found.length === 0) {
      return json({ error: `no data for ${account}`, try: "/" }, 404);
    }

    const body = {
      account,
      split_kind: splitKind,
      stats: found.map(derive),
    };
    return json(splitKind === "overall" ? { ...body, stats: body.stats[0] } : body);
  },
};
