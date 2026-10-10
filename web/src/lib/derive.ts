import type { Game, TDPlayer, ValueRow } from "../types";
import type { ProbView } from "./store";

export const label = (g: Game) => `${g.away.team} @ ${g.home.team}`;

export function shownProbs(g: Game, view: ProbView) {
  const model = g.prediction.p_home;
  const market = g.market?.home_no_vig ?? null;
  if (view === "market" && market != null) return { pHome: market, tickHome: model, tickIs: "model" as const };
  return { pHome: model, tickHome: market, tickIs: "market" as const };
}

export const valuesAbove = (g: Game, minEdge: number): ValueRow[] =>
  (g.values ?? []).filter((v) => v.edge_pp >= minEdge).sort((a, b) => b.edge_pp - a.edge_pp);

export interface Alert { game: Game; kind: "injury" | "qb" | "weather"; severity: 1 | 2; text: string; team?: string }

export function alertsFor(g: Game): Alert[] {
  const out: Alert[] = [];
  if (g.result) return out;
  for (const side of ["away", "home"] as const) {
    const s = g[side];
    for (const i of s.injuries ?? []) {
      if (["Other", "K", "P"].includes(i.group)) continue;
      const qb = s.qb.id === i.player_id;
      if (i.status === "Out" || i.status === "Doubtful" || i.status === "Questionable" || (!i.designated && i.practice === "DNP")) {
        const st = i.designated ? i.status : `${i.practice} at practice, no game status yet`;
        out.push({ game: g, kind: qb ? "qb" : "injury", severity: qb || i.status === "Out" ? 2 : 1, team: s.team,
          text: `${s.team} ${i.position} ${i.name}: ${st}${i.injury ? ` (${i.injury})` : ""}` });
      }
    }
  }
  const w = g.weather;
  if (w?.status === "forecast") {
    if ((w.wind_mph ?? 0) >= 15) out.push({ game: g, kind: "weather", severity: 2, text: `Wind ${w.wind_mph?.toFixed(0)} mph forecast (gusts ${w.gust_mph?.toFixed(0)})` });
    if ((w.precip_prob_pct ?? 0) >= 50) out.push({ game: g, kind: "weather", severity: 1, text: `${w.precip_prob_pct}% chance of ${(w.snow_in ?? 0) > 0 ? "snow" : "rain"}` });
    if ((w.temp_f ?? 60) <= 25) out.push({ game: g, kind: "weather", severity: 1, text: `${w.temp_f?.toFixed(0)}°F at kickoff` });
  }
  return out;
}

export function isUncertainGame(g: Game): boolean {
  const r = g.confidence?.reasons ?? [];
  return r.some((x) => /QB|Wind|questionable|not practising/i.test(x));
}

export const UNCERTAIN = new Set(["Questionable", "Doubtful"]);

/** Player probability under the chosen availability scenario; null = player excluded in that scenario. */
export function tdP(t: TDPlayer, withoutUncertain: boolean): number | null {
  if (!withoutUncertain) return t.p;
  if (UNCERTAIN.has(t.status)) return null;
  return t.p_if_uncertain_out ?? t.p;
}

export function tdEV(t: TDPlayer, p: number | null): number | null {
  if (!t.market || p == null) return null;
  const d = t.market.odds > 0 ? 1 + t.market.odds / 100 : 1 + 100 / -t.market.odds;
  return p * (d - 1) - (1 - p);
}
