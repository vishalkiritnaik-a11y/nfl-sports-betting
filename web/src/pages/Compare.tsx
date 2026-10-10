import { useState } from "react";
import { useApp } from "../App";
import { Note, Section, TeamMark } from "../components/ui";
import { num, pct } from "../lib/format";
import { tdP } from "../lib/derive";
import { useSettings } from "../lib/store";
import type { Game, Side, TDPlayer } from "../types";

function sideOf(games: Game[], team: string): { s: Side; g: Game; p: number } | null {
  for (const g of games) {
    if (g.home.team === team) return { s: g.home, g, p: g.prediction.p_home };
    if (g.away.team === team) return { s: g.away, g, p: g.prediction.p_away };
  }
  return null;
}

const TEAM_ROWS: [string, (x: { s: Side; g: Game; p: number }) => string][] = [
  ["Opponent", (x) => (x.g.home.team === x.s.team ? `vs ${x.g.away.team}` : `at ${x.g.home.team}`)],
  ["Record", (x) => x.s.record],
  ["Win probability", (x) => pct(x.p, 1)],
  ["Projected points", (x) => num(x.g.home.team === x.s.team ? x.g.prediction.home_pts : x.g.prediction.away_pts)],
  ["Elo rating", (x) => num(x.s.elo, 0)],
  ["Starting QB", (x) => `${x.s.qb.name ?? "—"} (${x.s.qb.epa_db.toFixed(3)} EPA/db)`],
  ["Offense EPA/play (season)", (x) => num(x.s.season?.o_epa_play as number, 3)],
  ["Defense EPA/play allowed", (x) => num(x.s.season?.d_epa_play as number, 3)],
  ["Points per game", (x) => num(x.s.season?.o_points as number)],
  ["Points allowed per game", (x) => num(x.s.season?.d_points as number)],
  ["Red-zone TD rate", (x) => pct(x.s.season?.o_rz_td as number, 1)],
  ["Turnover differential", (x) => num(x.s.season?.to_diff as number, 0)],
  ["Last 5 record", (x) => x.s.form?.last5?.record ?? "—"],
  ["Rest days", (x) => String(x.s.rest_days)],
  ["Travel", (x) => `${Math.round(x.s.travel_km)} km`],
];

const PLAYER_ROWS: [string, (t: TDPlayer, wu: boolean) => string][] = [
  ["Team / opponent", (t) => `${t.team} vs ${t.opp}`],
  ["Anytime TD", (t, wu) => pct(tdP(t, wu), 1)],
  ["Rushing / receiving path", (t) => `${pct(t.lam_rush / Math.max(1e-6, t.lam_rush + t.lam_rec))} / ${pct(t.lam_rec / Math.max(1e-6, t.lam_rush + t.lam_rec))}`],
  ["Status", (t) => t.status],
  ["Season TDs", (t) => String(t.recent?.season_tds ?? "—")],
  ["TDs last 3 / 5 / 10", (t) => (t.recent ? `${t.recent.last3} / ${t.recent.last5} / ${t.recent.last10}` : "—")],
  ["Carries inside 10 (season)", (t) => String(t.recent?.season_i10_carries ?? "—")],
  ["Red-zone targets (season)", (t) => String(t.recent?.season_rz_targets ?? "—")],
  ["Target share", (t) => pct(t.usage?.share_targets ?? null)],
  ["Carry share", (t) => pct(t.usage?.share_carries ?? null)],
  ["Snap share, last 3", (t) => t.snap_pct_last3?.map((x) => pct(x)).join(", ") || "—"],
  ["Team projected points", (t) => num(t.team_exp_points)],
  ["Opponent TDs allowed to position", (t) => (t.opp_vs_pos ? `${t.opp_vs_pos.td_pg.toFixed(2)}/g` : "—")],
  ["Confidence", (t) => t.confidence?.label ?? "—"],
];

export default function Compare() {
  const { meta, week } = useApp();
  const { withoutUncertain } = useSettings();
  const games = week!.games;
  const teams = [...new Set(games.flatMap((g) => [g.away.team, g.home.team]))].sort();
  const players = [...week!.td].sort((a, b) => a.name.localeCompare(b.name));
  const [a, setA] = useState(games[0]?.away.team ?? "");
  const [b, setB] = useState(games[0]?.home.team ?? "");
  const [pa, setPa] = useState(players[0]?.player_id ?? "");
  const [pb, setPb] = useState(players[1]?.player_id ?? "");
  const A = sideOf(games, a), B = sideOf(games, b);
  const PA = players.find((t) => t.player_id === pa), PB = players.find((t) => t.player_id === pb);
  return (
    <div className="grid gap-5">
      <h1 className="display text-[30px] leading-tight">Compare</h1>
      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Two teams">
          <div className="flex gap-3 mb-3 flex-wrap">
            {[[a, setA], [b, setB]].map(([v, set], i) => (
              <select key={i} value={v as string} onChange={(e) => (set as (s: string) => void)(e.target.value)} aria-label={`Team ${i + 1}`} className="max-w-[200px]">
                {teams.map((t) => <option key={t} value={t}>{meta.teams[t]?.name ?? t}</option>)}
              </select>))}
          </div>
          {A && B ? (
            <div className="scroll-x"><table className="dtable text-[14px]"><thead><tr><th /><th><span className="flex items-center gap-2"><TeamMark team={a} info={meta.teams[a]} size={20} />{a}</span></th><th><span className="flex items-center gap-2"><TeamMark team={b} info={meta.teams[b]} size={20} />{b}</span></th></tr></thead>
              <tbody>{TEAM_ROWS.map(([l, f]) => <tr key={l}><td className="text-muted">{l}</td><td className="tnum">{f(A)}</td><td className="tnum">{f(B)}</td></tr>)}</tbody></table></div>
          ) : <Note>Pick two teams playing this week.</Note>}
        </Section>
        <Section title="Two players">
          {players.length < 2 ? <Note>No player projections this week.</Note> : <>
            <div className="flex gap-3 mb-3 flex-wrap">
              {[[pa, setPa], [pb, setPb]].map(([v, set], i) => (
                <select key={i} value={v as string} onChange={(e) => (set as (s: string) => void)(e.target.value)} aria-label={`Player ${i + 1}`} className="max-w-[220px]">
                  {players.map((t) => <option key={t.player_id + t.game_id} value={t.player_id}>{t.name} ({t.team} {t.position})</option>)}
                </select>))}
            </div>
            {PA && PB && <div className="scroll-x"><table className="dtable text-[14px]"><thead><tr><th /><th>{PA.name}</th><th>{PB.name}</th></tr></thead>
              <tbody>{PLAYER_ROWS.map(([l, f]) => <tr key={l}><td className="text-muted">{l}</td><td className="tnum">{f(PA, withoutUncertain)}</td><td className="tnum">{f(PB, withoutUncertain)}</td></tr>)}</tbody></table></div>}
            <p className="text-xs text-muted mt-2">A higher probability isn't automatically a better bet. That depends on the price.</p>
          </>}
        </Section>
      </div>
    </div>
  );
}
