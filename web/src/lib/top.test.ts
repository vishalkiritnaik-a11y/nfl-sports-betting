import { describe, expect, it } from "vitest";
import { topPicks } from "./top";
import type { Game, Rec } from "../types";

const rec = (market: Rec["market"], score: number, ev: number): Rec => ({
  market, side: "X", label: `${market} ${score}`, line: null, odds: -110, score,
  verdict: score >= 7 ? "Bet" : score === 6 ? "Lean" : "Pass", p_model: 0.5, p_market: 0.5, p_win: 0.5, ev, other_score: 4, why: [],
});
const game = (id: string, recs: Rec[], done = false, ko = "2026-10-18T17:00:00Z") => ({
  game_id: id, kickoff_utc: ko, result: done ? { home_score: 1, away_score: 0, winner: "H", model_correct: null } : undefined,
  recs: { markets: Object.fromEntries(recs.map((r) => [r.market, r])), opening: null, notes: null },
}) as unknown as Game;

describe("topPicks", () => {
  it("takes one pick per game, ranked by score then EV, skipping finished games", () => {
    const gs = [
      game("a", [rec("spread", 6, 0.01), rec("moneyline", 6, 0.03)]),
      game("b", [rec("total", 7, -0.02)]),
      game("c", [rec("spread", 5, 0.05)]),
      game("d", [rec("total", 9, 0.1)], true),
    ];
    const t = topPicks(gs, 5);
    expect(t.map((x) => x.game.game_id)).toEqual(["b", "a", "c"]);
    expect(t[1].rec.market).toBe("moneyline");
  });
  it("caps at n", () => {
    const gs = Array.from({ length: 8 }, (_, i) => game(`g${i}`, [rec("spread", 5, i / 100)]));
    expect(topPicks(gs, 5)).toHaveLength(5);
  });
});
