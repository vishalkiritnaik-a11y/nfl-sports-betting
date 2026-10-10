import { Link, useLocation } from "react-router-dom";
import type { Game, TeamInfo } from "../types";
import { ConfidenceTag, SplitBar, Star, TeamMark } from "./ui";
import { kickoffLocal, num, pct } from "../lib/format";
import { alertsFor, shownProbs, valuesAbove } from "../lib/derive";
import { fmtAmerican } from "../lib/odds";
import { useSettings } from "../lib/store";

function TeamRow({ g, side, p, teams }: { g: Game; side: "home" | "away"; p: number; teams: Record<string, TeamInfo> }) {
  const s = g[side];
  const won = g.result && g.result.winner === s.team;
  const score = g.result ? (side === "home" ? g.result.home_score : g.result.away_score) : null;
  return (
    <div className="flex items-center gap-3">
      <TeamMark team={s.team} info={teams[s.team]} size={30} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="display text-[19px]">{s.team}</span>
          <span className="text-xs text-muted tnum">{s.record}</span>
          {side === "home" && g.location !== "Neutral" && <span className="text-[11px] text-muted">home</span>}
        </div>
        <div className="text-xs text-muted truncate">{s.qb.name ?? "QB unknown"}{s.qb.changed ? " (new starter)" : ""}</div>
      </div>
      {score != null && <span className={`display text-[19px] tnum ${won ? "" : "text-muted"}`}>{score}</span>}
      <span className="display text-[22px] tnum w-[64px] text-right">{pct(p)}</span>
    </div>
  );
}

export default function MatchupCard({ g, teams }: { g: Game; teams: Record<string, TeamInfo> }) {
  const { probView, minEdge, watch, toggleGame } = useSettings();
  const { search } = useLocation();
  const { pHome, tickHome, tickIs } = shownProbs(g, probView);
  const k = kickoffLocal(g.kickoff_utc);
  const vals = g.result ? [] : valuesAbove(g, minEdge);
  const alerts = alertsFor(g);
  const major = alerts.filter((a) => a.severity === 2);
  const m = g.market;
  const pr = g.prediction;
  return (
    <Link to={{ pathname: `/game/${g.game_id}`, search }} className="panel p-4 block hover:border-[var(--muted)] transition-colors focus-visible:outline-2">
      <div className="flex items-center justify-between text-xs text-muted mb-3 gap-2">
        <span>{k.day}, {k.time}{g.venue.stadium ? ` at ${g.venue.stadium}` : ""}</span>
        <Star on={watch.games.includes(g.game_id)} onClick={() => toggleGame(g.game_id)} label={`${g.away.team} at ${g.home.team}`} />
      </div>
      <div className="space-y-2">
        <TeamRow g={g} side="away" p={1 - pHome} teams={teams} />
        <TeamRow g={g} side="home" p={pHome} teams={teams} />
      </div>
      <div className="mt-4 mb-1">
        <SplitBar pAway={1 - pHome} away={g.away.team} home={g.home.team} teams={teams} marketHome={tickHome}
          tickColor={tickIs === "market" ? "var(--market)" : "var(--model)"} tickLabel={tickIs === "market" ? "Market (no-vig)" : "Model"} />
      </div>
      <div className="flex justify-between text-[11.5px] text-muted mb-3">
        <span>{probView === "model" ? "Model" : "Market"} win probability{tickHome != null ? (tickIs === "market" ? ", brass tick = market" : ", blue tick = model") : ""}</span>
        {m?.home_no_vig != null && (
          <span className="tnum">model vs market {pr.p_home - m.home_no_vig >= 0 ? g.home.team : g.away.team} {Math.abs((pr.p_home - m.home_no_vig) * 100).toFixed(1)} pts</span>
        )}
      </div>
      <dl className="grid grid-cols-3 gap-2 text-[13px]">
        <div><dt className="text-muted text-[11.5px]">Projected</dt><dd className="tnum">{num(pr.away_pts, 0)}–{num(pr.home_pts, 0)}</dd></div>
        <div><dt className="text-muted text-[11.5px]">Spread / total</dt>
          <dd className="tnum">{m?.spread_line != null ? `${g.home.team} ${m.spread_line > 0 ? "-" : "+"}${Math.abs(m.spread_line)}` : "—"} / {m?.total_line ?? "—"}</dd></div>
        <div><dt className="text-muted text-[11.5px]">Moneyline</dt><dd className="tnum">{fmtAmerican(m?.away_moneyline)} / {fmtAmerican(m?.home_moneyline)}</dd></div>
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <ConfidenceTag c={g.confidence} />
        {vals.length > 0 && <span style={{ color: "var(--pos)" }}>{vals[0].selection} {vals[0].edge_pp > 0 ? "+" : ""}{vals[0].edge_pp.toFixed(1)} pts{vals.length > 1 ? `, +${vals.length - 1} more` : ""}</span>}
        {major.length > 0 && <span style={{ color: "var(--warn)" }}>{major.length} major alert{major.length > 1 ? "s" : ""}</span>}
        {g.lookahead && <span className="text-muted">Early look</span>}
        {g.result && <span className={g.result.model_correct ? "text-[var(--pos)]" : "text-[var(--neg)]"}>{g.result.model_correct ? "Model pick won" : g.result.model_correct === false ? "Model pick lost" : "Tie"}</span>}
      </div>
    </Link>
  );
}
