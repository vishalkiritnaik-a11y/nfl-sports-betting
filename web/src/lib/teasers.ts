import type { Game, TeaserStats } from "../types";

export type TeaserKind = "fav" | "dog";
export interface TeaserLeg {
  game: Game; team: string; kind: TeaserKind; line: number; teased: number;
  newsPts: number | null; newsText: string | null; items: number;
}

/** Points this side is favored by -> fav (7.5-8.5) / dog (getting 1.5-2.5) window, else null. */
export function kindFor(expMargin: number, s: Pick<TeaserStats, "fav_range" | "dog_range">): TeaserKind | null {
  if (expMargin >= s.fav_range[0] && expMargin <= s.fav_range[1]) return "fav";
  if (-expMargin >= s.dog_range[0] && -expMargin <= s.dog_range[1]) return "dog";
  return null;
}

export function breakEvenLeg(american: number): number {
  const dec = 1 + (american < 0 ? 100 / -american : american / 100);
  return Math.sqrt(1 / dec);
}

/** Qualifying legs among upcoming games. market.spread_line = expected home margin. */
export function teaserLegs(games: Game[], s: TeaserStats): TeaserLeg[] {
  const out: TeaserLeg[] = [];
  for (const g of games) {
    const sl = g.market?.spread_line;
    if (g.result || sl == null) continue;
    for (const [team, exp] of [[g.home.team, sl], [g.away.team, -sl]] as const) {
      const kind = kindFor(exp, s);
      if (!kind) continue;
      const sp = g.recs?.markets.spread;
      const news = sp?.why.find((w) => w.factor === "News");
      const newsPts = news ? (sp!.side === team ? news.points : -news.points) : null;
      out.push({ game: g, team, kind, line: -exp, teased: -exp + s.tease, newsPts, newsText: news?.text ?? null,
                 items: g.recs?.notes?.items?.length ?? 0 });
    }
  }
  return out.sort((a, b) => (a.kind === b.kind ? a.game.kickoff_utc.localeCompare(b.game.kickoff_utc) : a.kind === "dog" ? -1 : 1));
}

/** "clears" when both the long-run and recent hit rates beat break-even, "mixed" when one does. */
export function verdict(s: TeaserStats, kind: TeaserKind, price: number): "clears" | "mixed" | "below" {
  const be = breakEvenLeg(price), a = s.all[kind].hit ?? 0, r = s.recent[kind].hit ?? 0;
  return a >= be && r >= be ? "clears" : a >= be || r >= be ? "mixed" : "below";
}
