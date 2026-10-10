// Personal bet tracker. Bets live only in this browser (localStorage), never in the repo.
import type { Game, TDPlayer, WeekData } from "../types";
import { americanToDecimal, americanToImplied } from "./odds";

export type Market = "moneyline" | "spread" | "total" | "anytime_td";

export interface Alt {
  label: string; market: Market; side: string; line: number | null; odds: number | null;
  model_p: number; ev: number | null; player_id?: string;
}

export interface Bet {
  id: string; season: number; week: number; game_id: string; matchup: string; kickoff_utc: string;
  market: Market; side: string;            // team abbr, "over"/"under", or player_id
  label: string; line: number | null; odds: number; stake: number;
  model_p: number | null;                  // model probability when logged
  logged_at: string; snapshot_backtest: boolean;
  alts: Alt[];                             // every option in the game at logging time
}

export type Outcome = "won" | "lost" | "push" | "void" | "pending";

const KEY = "ne.bets";

export function loadBets(): Bet[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}
export function saveBets(b: Bet[]): boolean {
  try { localStorage.setItem(KEY, JSON.stringify(b)); return true; } catch { return false; }
}

const ev = (p: number, odds: number | null) => (odds == null ? null : p * (americanToDecimal(odds) - 1) - (1 - p));

/** All bettable options in a game with the model's probability, as of this data file. */
export function optionsFor(g: Game, td: TDPlayer[]): Alt[] {
  const out: Alt[] = [];
  const m = g.market, P = g.prediction, d = P.distribution;
  const H = g.home.team, A = g.away.team;
  out.push({ label: `${H} ML`, market: "moneyline", side: H, line: null, odds: m?.home_moneyline ?? null, model_p: P.p_home, ev: ev(P.p_home, m?.home_moneyline ?? null) });
  out.push({ label: `${A} ML`, market: "moneyline", side: A, line: null, odds: m?.away_moneyline ?? null, model_p: P.p_away, ev: ev(P.p_away, m?.away_moneyline ?? null) });
  if (m?.spread_line != null && d.p_home_cover != null) {
    const hl = -m.spread_line;
    out.push({ label: `${H} ${hl > 0 ? "+" : ""}${hl}`, market: "spread", side: H, line: hl, odds: m.home_spread_odds ?? null, model_p: d.p_home_cover, ev: ev(d.p_home_cover, m.home_spread_odds ?? null) });
    out.push({ label: `${A} ${-hl > 0 ? "+" : ""}${-hl}`, market: "spread", side: A, line: -hl, odds: m.away_spread_odds ?? null, model_p: 1 - d.p_home_cover, ev: ev(1 - d.p_home_cover, m.away_spread_odds ?? null) });
  }
  if (m?.total_line != null && d.p_over != null) {
    out.push({ label: `Over ${m.total_line}`, market: "total", side: "over", line: m.total_line, odds: m.over_odds ?? null, model_p: d.p_over, ev: ev(d.p_over, m.over_odds ?? null) });
    out.push({ label: `Under ${m.total_line}`, market: "total", side: "under", line: m.total_line, odds: m.under_odds ?? null, model_p: 1 - d.p_over, ev: ev(1 - d.p_over, m.under_odds ?? null) });
  }
  for (const t of td.filter((x) => x.game_id === g.game_id).sort((a, b) => b.p - a.p).slice(0, 12)) {
    out.push({ label: `${t.name} anytime TD`, market: "anytime_td", side: t.player_id, player_id: t.player_id, line: null, odds: t.market?.odds ?? null, model_p: t.p, ev: t.market ? ev(t.p, t.market.odds) : null });
  }
  return out;
}

/** Grade a selection against a final game. TD bets are void if the player didn't play. */
export function grade(market: Market, side: string, line: number | null, g: Game | undefined, td: TDPlayer[] | undefined): Outcome {
  if (!g?.result) return "pending";
  const hs = g.result.home_score, as = g.result.away_score;
  if (market === "moneyline") {
    if (hs === as) return "push";
    return (side === g.home.team) === (hs > as) ? "won" : "lost";
  }
  if (market === "spread" && line != null) {
    const margin = side === g.home.team ? hs - as : as - hs;
    const v = margin + line;
    return v > 0 ? "won" : v < 0 ? "lost" : "push";
  }
  if (market === "total" && line != null) {
    const t = hs + as;
    if (t === line) return "push";
    return (side === "over") === (t > line) ? "won" : "lost";
  }
  if (market === "anytime_td") {
    const p = td?.find((x) => x.game_id === g.game_id && x.player_id === side);
    if (!p || p.scored == null) return "void";
    return p.scored ? "won" : "lost";
  }
  return "pending";
}

export function profit(o: Outcome, odds: number, stake: number): number {
  if (o === "won") return stake * (americanToDecimal(odds) - 1);
  if (o === "lost") return -stake;
  return 0;
}

export function breakEven(odds: number) { return americanToImplied(odds); }

export function newBet(g: Game, wk: WeekData, opt: Alt, odds: number, stake: number, line: number | null): Bet {
  return {
    id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    season: wk.season, week: wk.week, game_id: g.game_id, matchup: `${g.away.team} @ ${g.home.team}`, kickoff_utc: g.kickoff_utc,
    market: opt.market, side: opt.side, label: opt.market === "total" ? `${opt.side === "over" ? "Over" : "Under"} ${line}` :
      opt.market === "spread" ? `${opt.side} ${line != null && line > 0 ? "+" : ""}${line}` : opt.label,
    line, odds, stake, model_p: opt.model_p, logged_at: new Date().toISOString(),
    snapshot_backtest: !!g.result || g.prediction.backtest, alts: optionsFor(g, wk.td),
  };
}

/** Parse a share link like ?add=2026_05_PHI_JAX:total:over:41.5:-112 */
export function parseAdd(s: string): { game_id: string; market: Market; side: string; line: number | null; odds: number | null } | null {
  const [game_id, market, side, line, odds] = s.split(":");
  if (!game_id || !market || !side) return null;
  if (!["moneyline", "spread", "total", "anytime_td"].includes(market)) return null;
  const n = (x?: string) => (x == null || x === "" ? null : Number(x));
  return { game_id, market: market as Market, side, line: n(line), odds: n(odds) };
}
