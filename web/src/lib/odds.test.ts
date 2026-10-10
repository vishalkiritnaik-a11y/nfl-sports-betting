import { describe, expect, it } from "vitest";
import { americanToDecimal, americanToImplied, expectedProfit, isValue, probToAmerican, removeVig } from "./odds";

describe("odds math", () => {
  it("implied probability from American odds", () => {
    expect(americanToImplied(150)).toBeCloseTo(100 / 250, 10);
    expect(americanToImplied(-150)).toBeCloseTo(150 / 250, 10);
    expect(americanToImplied(-110)).toBeCloseTo(110 / 210, 10);
    expect(() => americanToImplied(50)).toThrow();
  });
  it("decimal conversion agrees with implied", () => {
    for (const a of [-400, -110, 100, 250]) expect(1 / americanToDecimal(a)).toBeCloseTo(americanToImplied(a), 10);
  });
  it("vig removal sums to one", () => {
    const f = removeVig([americanToImplied(-110), americanToImplied(-110)]);
    expect(f[0] + f[1]).toBeCloseTo(1, 12);
    expect(f[0]).toBeCloseTo(0.5, 12);
  });
  it("expected profit formula", () => {
    expect(expectedProfit(0.5, 2)).toBeCloseTo(0, 12);
    expect(expectedProfit(0.25, 5)).toBeCloseTo(0.25, 12);
  });
  it("value threshold", () => {
    expect(isValue(0.56, 0.52, 3)).toBe(true);
    expect(isValue(0.54, 0.52, 3)).toBe(false);
  });
  it("fair odds", () => {
    expect(probToAmerican(0.5)).toBe(100);
    expect(probToAmerican(0.6)).toBe(-150);
  });
});
