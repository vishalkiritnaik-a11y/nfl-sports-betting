import type { Game, Rec } from "../types";

export interface TopPick { game: Game; rec: Rec }

/** The week's strongest picks across every upcoming game.
 *  One pick per game (its best market), so five picks are five separate games rather than
 *  three correlated bets on the same matchup. Ranked by score, then market-anchored EV.
 *  Verdicts are left untouched: if fewer than `n` picks clear Bet/Lean, the rest show as Pass. */
export function topPicks(games: Game[], n = 5): TopPick[] {
  const best: TopPick[] = [];
  for (const g of games) {
    if (g.result || !g.recs) continue;
    const rs = Object.values(g.recs.markets).filter((r): r is Rec => !!r);
    if (!rs.length) continue;
    rs.sort(byStrength);
    best.push({ game: g, rec: rs[0] });
  }
  return best.sort((a, b) => byStrength(a.rec, b.rec) || a.game.kickoff_utc.localeCompare(b.game.kickoff_utc)).slice(0, n);
}

function byStrength(a: Rec, b: Rec): number {
  return b.score - a.score || b.ev - a.ev;
}
