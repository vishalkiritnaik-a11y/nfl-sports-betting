import { describe, expect, it } from "vitest";
import { grade, parseAdd, profit } from "./bets";
import type { Game } from "../types";

const game = (hs: number, as: number) => ({ game_id: "g", home: { team: "JAX" }, away: { team: "PHI" },
  result: { home_score: hs, away_score: as, winner: "", model_correct: null } }) as unknown as Game;

describe("bet grading", () => {
  it("totals, including pushes", () => {
    expect(grade("total", "over", 41.5, game(24, 20), [])).toBe("won");
    expect(grade("total", "over", 41.5, game(21, 17), [])).toBe("lost");
    expect(grade("total", "under", 41, game(21, 20), [])).toBe("push");
  });
  it("spreads from the bet team's side", () => {
    expect(grade("spread", "PHI", 7.5, game(24, 17), [])).toBe("won");   // PHI lost by 7, +7.5 covers
    expect(grade("spread", "JAX", -7.5, game(24, 17), [])).toBe("lost");
    expect(grade("spread", "JAX", -7, game(24, 17), [])).toBe("push");
  });
  it("moneyline and pending", () => {
    expect(grade("moneyline", "JAX", null, game(24, 17), [])).toBe("won");
    expect(grade("moneyline", "PHI", null, { ...game(0, 0), result: undefined } as unknown as Game, [])).toBe("pending");
  });
  it("anytime TD voids when the player didn't play", () => {
    const td = [{ game_id: "g", player_id: "p1", scored: 1 }, { game_id: "g", player_id: "p2", scored: 0 }] as never[];
    expect(grade("anytime_td", "p1", null, game(24, 17), td)).toBe("won");
    expect(grade("anytime_td", "p2", null, game(24, 17), td)).toBe("lost");
    expect(grade("anytime_td", "p3", null, game(24, 17), td)).toBe("void");
  });
  it("profit at American odds", () => {
    expect(profit("won", -112, 1)).toBeCloseTo(100 / 112, 10);
    expect(profit("won", 310, 2)).toBeCloseTo(6.2, 10);
    expect(profit("lost", -112, 1)).toBe(-1);
    expect(profit("push", -112, 1)).toBe(0);
  });
  it("parses share links", () => {
    expect(parseAdd("2026_05_PHI_JAX:total:over:41.5:-112")).toEqual({ game_id: "2026_05_PHI_JAX", market: "total", side: "over", line: 41.5, odds: -112 });
    expect(parseAdd("bad")).toBeNull();
  });
});
