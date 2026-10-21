import { describe, expect, it } from "vitest";
import { breakEvenLeg, kindFor, teaserLegs, verdict } from "./teasers";
import type { Game, TeaserStats } from "../types";

const S: TeaserStats = {
  generated: "", tease: 6, fav_range: [7.5, 8.5], dog_range: [1.5, 2.5],
  periods: { all: { from: 2016, to: 2026 }, recent: { from: 2023, to: 2026 } },
  all: { fav: { n: 230, hit: 0.713 }, dog: { n: 445, hit: 0.775 }, both: { n: 675, hit: 0.754 } },
  recent: { fav: { n: 73, hit: 0.616 }, dog: { n: 200, hit: 0.775 }, both: { n: 273, hit: 0.733 } },
  break_even: {},
};
const game = (id: string, sl: number | null, done = false) => ({
  game_id: id, kickoff_utc: "2026-10-25T17:00:00Z", home: { team: "H" }, away: { team: "A" },
  market: sl == null ? null : { source: "x", spread_line: sl },
  result: done ? { home_score: 1, away_score: 0, winner: "H", model_correct: null } : undefined,
}) as unknown as Game;

describe("teasers", () => {
  it("classifies windows", () => {
    expect(kindFor(8, S)).toBe("fav");
    expect(kindFor(-2.5, S)).toBe("dog");
    expect(kindFor(3, S)).toBeNull();
    expect(kindFor(9, S)).toBeNull();
  });
  it("break-even per leg for a 2-team teaser", () => {
    expect(breakEvenLeg(-120)).toBeCloseTo(0.7385, 3);
    expect(breakEvenLeg(-110)).toBeCloseTo(0.7237, 3);
  });
  it("finds both legs of a 2-point game and the favorite of an 8-point game, skipping finished games", () => {
    const legs = teaserLegs([game("a", 2), game("b", -8), game("c", 2, true), game("d", null)], S);
    expect(legs.map((l) => [l.game.game_id, l.team, l.kind, l.teased])).toEqual([["a", "A", "dog", 8], ["b", "A", "fav", -2]]);
  });
  it("judges underdog legs as clearing -120 and favorites as below", () => {
    expect(verdict(S, "dog", -120)).toBe("clears");
    expect(verdict(S, "fav", -120)).toBe("below");
    expect(verdict(S, "dog", -140)).toBe("clears");
  });
});
