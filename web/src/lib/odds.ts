// Client-side odds math. Mirrors pipeline/nfledge/odds.py (tested in both places).

export function americanToImplied(odds: number): number {
  if (odds > -100 && odds < 100) throw new Error(`invalid American odds ${odds}`);
  return odds > 0 ? 100 / (odds + 100) : -odds / (-odds + 100);
}

export function americanToDecimal(odds: number): number {
  if (odds > -100 && odds < 100) throw new Error(`invalid American odds ${odds}`);
  return odds > 0 ? 1 + odds / 100 : 1 + 100 / -odds;
}

export function probToAmerican(p: number): number {
  if (p <= 0 || p >= 1) throw new Error("p must be in (0,1)");
  const d = 1 / p;
  return d >= 2 ? Math.round((d - 1) * 100) : Math.round(-100 / (d - 1));
}

export function removeVig(implied: number[]): number[] {
  const s = implied.reduce((a, b) => a + b, 0);
  return implied.map((p) => p / s);
}

/** Expected profit per 1 unit staked: p*(D-1) - (1-p). */
export function expectedProfit(p: number, decimal: number): number {
  return p * (decimal - 1) - (1 - p);
}

export function edgePP(modelP: number, marketP: number): number {
  return (modelP - marketP) * 100;
}

export function isValue(modelP: number, marketP: number, minEdgePP: number): boolean {
  return edgePP(modelP, marketP) >= minEdgePP;
}

export function fmtAmerican(o: number | null | undefined): string {
  if (o == null || Number.isNaN(o)) return "—";
  return o > 0 ? `+${Math.round(o)}` : `${Math.round(o)}`;
}
