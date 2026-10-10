import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useApp } from "../App";
import { ContributionChart, HistoryChart, MarginHist } from "../components/charts";
import TDTable from "../components/TDTable";
import { ConfidenceTag, Edge, Note, Section, SortTable, SplitBar, Star, StatusTag, TeamMark, Toggle, type Col } from "../components/ui";
import { alertsFor } from "../lib/derive";
import { kickoffLocal, num, pct, signed, visibleColor } from "../lib/format";
import { fmtAmerican } from "../lib/odds";
import { useSettings } from "../lib/store";
import type { Game, MatchupRow, Side, TeamInfo, ValueRow, Weather } from "../types";

const STAT_ROWS: [string, string, (v: number) => string, "high" | "low"][] = [
  ["o_points", "Points per game", (v) => v.toFixed(1), "high"],
  ["o_epa_play", "EPA per play", (v) => v.toFixed(3), "high"],
  ["o_success", "Success rate", (v) => pct(v, 1), "high"],
  ["o_pass_epa", "Pass EPA / dropback", (v) => v.toFixed(3), "high"],
  ["o_rush_epa", "Rush EPA / carry", (v) => v.toFixed(3), "high"],
  ["o_ypp", "Yards per play", (v) => v.toFixed(2), "high"],
  ["o_explosive", "Explosive play rate", (v) => pct(v, 1), "high"],
  ["o_third_conv", "3rd-down conversion", (v) => pct(v, 1), "high"],
  ["o_fourth_conv", "4th-down conversion", (v) => pct(v, 1), "high"],
  ["o_rz_td", "Red-zone TD rate", (v) => pct(v, 1), "high"],
  ["o_to_rate", "Turnovers per play", (v) => pct(v, 2), "low"],
  ["o_sack_rate", "Sack rate allowed", (v) => pct(v, 1), "low"],
  ["o_pressure_rate", "Pressure allowed", (v) => pct(v, 1), "low"],
  ["o_st_epa", "Special teams EPA / game", (v) => v.toFixed(2), "high"],
  ["o_plays_pg", "Plays per game", (v) => v.toFixed(1), "high"],
  ["o_top_min", "Time of possession (min)", (v) => v.toFixed(1), "high"],
  ["o_pass_rate", "Dropback rate", (v) => pct(v, 1), "high"],
];

function StatCompare({ g, which }: { g: Game; which: "season" | "blended" }) {
  const H = g.home[which] ?? {}, A = g.away[which] ?? {};
  const row = (k: string, lab: string, f: (v: number) => string, better: "high" | "low") => {
    const a = A[k] as number | null | undefined, h = H[k] as number | null | undefined;
    const best = a != null && h != null && a !== h ? ((better === "high") === (a > h) ? "a" : "h") : null;
    return (
      <tr key={k}>
        <td className="text-right tnum" style={{ color: best === "a" ? "var(--fg)" : "var(--muted)", fontWeight: best === "a" ? 600 : 400 }}>{a != null ? f(a) : "—"}</td>
        <td className="text-center text-muted text-[13px]">{lab}</td>
        <td className="tnum" style={{ color: best === "h" ? "var(--fg)" : "var(--muted)", fontWeight: best === "h" ? 600 : 400 }}>{h != null ? f(h) : "—"}</td>
      </tr>
    );
  };
  const defs: [string, string, (v: number) => string, "high" | "low"][] = [
    ["d_points", "Points allowed / game", (v) => v.toFixed(1), "low"], ["d_epa_play", "EPA / play allowed", (v) => v.toFixed(3), "low"],
    ["d_success", "Success rate allowed", (v) => pct(v, 1), "low"], ["d_pass_epa", "Pass EPA allowed", (v) => v.toFixed(3), "low"],
    ["d_rush_epa", "Rush EPA allowed", (v) => v.toFixed(3), "low"], ["d_explosive", "Explosive plays allowed", (v) => pct(v, 1), "low"],
    ["d_rz_td", "Red-zone TD rate allowed", (v) => pct(v, 1), "low"], ["d_to_rate", "Takeaways per play", (v) => pct(v, 2), "high"],
    ["d_sack_rate", "Sack rate", (v) => pct(v, 1), "high"], ["d_pressure_rate", "Pressure rate", (v) => pct(v, 1), "high"],
    ["d_third_conv", "3rd-down conv. allowed", (v) => pct(v, 1), "low"],
  ];
  return (
    <div className="scroll-x">
      <table className="grid text-[14px]">
        <thead><tr><th className="text-right" style={{ textAlign: "right" }}>{g.away.team}</th><th style={{ textAlign: "center" }}>Offense</th><th>{g.home.team}</th></tr></thead>
        <tbody>{STAT_ROWS.map((r) => row(...r))}</tbody>
        <thead><tr><th /><th style={{ textAlign: "center" }}>Defense</th><th /></tr></thead>
        <tbody>{defs.map((r) => row(...r))}
          {which === "season" && <tr><td className="text-right tnum">{signed(A.to_diff as number, 0)}</td><td className="text-center text-muted text-[13px]">Turnover differential</td><td className="tnum">{signed(H.to_diff as number, 0)}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function MatchupTable({ rows, off, def }: { rows: MatchupRow[]; off: string; def: string }) {
  const f = (k: string, v: number) => (k.includes("rate") ? pct(v, 1) : v.toFixed(3));
  return (
    <div className="scroll-x">
      <table className="grid text-[13.5px]">
        <thead><tr><th>Dimension</th><th style={{ textAlign: "right" }}>{off} offense</th><th style={{ textAlign: "right" }}>{def} defense allows</th><th>Read</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.key}>
            <td>{r.label}</td>
            <td className="text-right tnum">{f(r.key, r.off_value)} <span className="text-muted text-xs">#{r.off_rank}, n={r.off_n}</span></td>
            <td className="text-right tnum">{f(r.key, r.def_value)} <span className="text-muted text-xs">#{r.def_rank}, n={r.def_n}</span></td>
            <td style={{ color: r.verdict === "favours offense" ? "var(--pos)" : r.verdict === "favours defense" ? "var(--neg)" : "var(--muted)" }}>{r.verdict}</td>
          </tr>))}
        </tbody>
      </table>
    </div>
  );
}

function WeatherCard({ w, g }: { w?: Weather; g: Game }) {
  if (!w) return <Note>No weather data.</Note>;
  if (w.status === "indoor") return <Note>Indoor stadium ({g.venue.stadium}). Weather doesn't apply.</Note>;
  if (w.status === "observed") return <Note>Recorded at the game: {w.temp_f != null ? `${w.temp_f}°F` : "temperature n/a"}, wind {w.wind_mph ?? "n/a"} mph, roof {w.roof ?? "n/a"}. Source: {w.source}.</Note>;
  if (w.status === "beyond_forecast_range") return <Note>Kickoff is more than 16 days out, beyond the forecast range.</Note>;
  if (w.status === "unavailable") return <Note>Forecast unavailable for this build{w.roof_type ? ` (${w.roof_type} venue)` : ""}. It refreshes on the next scheduled run.</Note>;
  return (
    <div className="grid gap-2 text-sm">
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 tnum">
        <div><dt className="text-xs text-muted">Temperature</dt><dd>{num(w.temp_f, 0)}°F{w.temp_range_f ? <span className="text-muted text-xs"> ({w.temp_range_f[0]}–{w.temp_range_f[1]})</span> : null}</dd></div>
        <div><dt className="text-xs text-muted">Wind (max in game window)</dt><dd>{num(w.wind_mph, 0)} mph, gusts {num(w.gust_mph, 0)}{w.wind_range_mph ? <span className="text-muted text-xs"> (range {w.wind_range_mph[0]}–{w.wind_range_mph[1]})</span> : null}</dd></div>
        <div><dt className="text-xs text-muted">Precipitation</dt><dd>{w.precip_prob_pct ?? 0}% chance, {num(w.precip_in, 2)} in{(w.snow_in ?? 0) > 0 ? `, ${w.snow_in} in snow` : ""}</dd></div>
        <div><dt className="text-xs text-muted">Humidity</dt><dd>{w.humidity_pct ?? "—"}%</dd></div>
      </dl>
      <p className="text-xs text-muted">Forecast from {w.source}, {w.lead_hours != null ? `${Math.round(w.lead_hours)} hours before kickoff` : ""}. Ranges are the 10th–90th percentile of the GFS ensemble. {w.roof_note ?? ""}
        {g.prediction.weather_total_delta != null && ` Applying the forecast to the totals model moves the projected total by ${signed(g.prediction.weather_total_delta, 1)} points; that effect is learned from past outdoor games, not assumed.`}</p>
    </div>
  );
}

function InjuryList({ s }: { s: Side }) {
  const list = (s.injuries ?? []).filter((i) => i.designated || i.practice === "DNP" || i.practice === "Limited");
  if (!list.length) return <Note>No designations or limited practices reported.</Note>;
  return (
    <ul className="grid gap-1 text-[13.5px]">
      {list.map((i) => (
        <li key={i.player_id} className="flex items-center gap-2">
          <span className="w-9 text-muted text-xs">{i.position}</span>
          <span className="flex-1">{i.name}{s.qb.id === i.player_id ? " (starting QB)" : ""}<span className="text-muted text-xs">{i.injury ? `, ${i.injury}` : ""}</span></span>
          {i.designated ? <StatusTag s={i.status} /> : <span className="text-xs text-muted">no game status</span>}
          <span className="text-xs text-muted w-16 text-right">{i.practice || "—"}</span>
        </li>))}
    </ul>
  );
}

const vcols: Col<ValueRow>[] = [
  { key: "sel", label: "Selection", sort: (v) => v.selection, render: (v) => <span className="font-medium">{v.selection}</span> },
  { key: "odds", label: "Price", align: "right", sort: (v) => v.odds, render: (v) => fmtAmerican(v.odds) },
  { key: "model", label: "Model", align: "right", sort: (v) => v.model_p, render: (v) => <span style={{ color: "var(--model)" }}>{pct(v.model_p, 1)}</span> },
  { key: "raw", label: "Implied (raw)", align: "right", sort: (v) => v.raw_implied, render: (v) => pct(v.raw_implied, 1) },
  { key: "nv", label: "No-vig market", align: "right", sort: (v) => v.no_vig, render: (v) => <span style={{ color: "var(--market)" }}>{pct(v.no_vig, 1)}</span> },
  { key: "edge", label: "Edge (pts)", align: "right", sort: (v) => v.edge_pp, render: (v) => <Edge v={v.edge_pp} /> },
  { key: "ev", label: "EV / unit", align: "right", sort: (v) => v.ev_per_unit, render: (v) => <Edge v={v.ev_per_unit} /> },
  { key: "roi", label: "ROI", align: "right", sort: (v) => v.roi_pct, render: (v) => <Edge v={v.roi_pct} /> },
];

export default function GamePage() {
  const { id } = useParams();
  const { meta, week } = useApp();
  const { search } = useLocation();
  const { watch, toggleGame, minEdge, withoutUncertain, setWithoutUncertain } = useSettings();
  const [statView, setStatView] = useState<"season" | "blended">("season");
  const [showRaw, setShowRaw] = useState(false);
  const g = week!.games.find((x) => x.game_id === id);
  if (!g) return <div className="panel p-6">That game isn't in the selected week. <Link className="link" to={{ pathname: "/", search }}>Back to the slate</Link></div>;
  const T: Record<string, TeamInfo> = meta.teams;
  const pr = g.prediction, m = g.market;
  const k = kickoffLocal(g.kickoff_utc);
  const td = week!.td.filter((t) => t.game_id === g.game_id);
  const homeC = visibleColor(T[g.home.team]?.color, T[g.home.team]?.color2), awayC = visibleColor(T[g.away.team]?.color, T[g.away.team]?.color2);
  const fav = pr.p_home >= 0.5 ? g.home.team : g.away.team;
  const alerts = alertsFor(g);
  return (
    <div className="grid gap-5">
      <Link to={{ pathname: "/", search }} className="text-sm text-muted hover:text-fg w-fit">← Back to the slate</Link>
      <header className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted mb-4">
          <span>{k.day}, {k.time}. {g.venue.stadium}{g.location === "Neutral" ? " (neutral site)" : ""}. {g.venue.roof ?? g.venue.roof_type ?? ""}{g.venue.surface ? `, ${g.venue.surface}` : ""}{g.div_game ? ". Division game" : ""}</span>
          <span className="flex items-center gap-3"><ConfidenceTag c={g.confidence} /><Star on={watch.games.includes(g.game_id)} onClick={() => toggleGame(g.game_id)} label={g.game_id} /></span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-4">
          {(["away", "home"] as const).map((side, i) => {
            const s = g[side];
            const p = side === "home" ? pr.p_home : pr.p_away;
            const box = (
              <div key={side} className={`flex items-center gap-3 min-w-0 ${i === 1 ? "sm:flex-row-reverse sm:text-right" : ""}`}>
                <TeamMark team={s.team} info={T[s.team]} size={56} />
                <div>
                  <div className="display text-[26px] sm:text-[34px] leading-none">{T[s.team]?.nick ?? s.team}</div>
                  <div className="text-sm text-muted">{s.record}, {s.qb.name}{s.qb.changed ? " (new starter)" : ""}</div>
                  <div className="display text-[34px] sm:text-[44px] tnum leading-tight" style={{ color: "var(--model)" }}>{pct(p, 1)}</div>
                </div>
              </div>);
            return i === 0 ? [box, <div key="v" className="text-muted sm:text-center">{g.result ? <span className="display text-[30px] text-fg tnum">{g.result.away_score}–{g.result.home_score}</span> : "at"}</div>] : box;
          })}
        </div>
        <div className="mt-5"><SplitBar pAway={pr.p_away} away={g.away.team} home={g.home.team} teams={T} marketHome={m?.home_no_vig} height={14} /></div>
        <div className="flex flex-wrap justify-between gap-2 mt-2 text-xs text-muted">
          <span>Model win probability{m?.home_no_vig != null ? `; brass tick is the no-vig market (${g.home.team} ${pct(m.home_no_vig, 1)})` : ""}</span>
          <span>{pr.tie_note}</span>
        </div>
        {pr.backtest && <p className="text-xs text-muted mt-2">Backtest: generated by a model trained on {pr.trained_on} using only data available before kickoff.</p>}
      </header>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Prediction summary">
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4 tnum text-sm">
            <div><dt className="text-xs text-muted">Projected score</dt><dd className="display text-[22px]">{g.away.team} {num(pr.away_pts, 0)}, {g.home.team} {num(pr.home_pts, 0)}</dd></div>
            <div><dt className="text-xs text-muted">Projected margin</dt><dd className="text-[18px]">{fav} by {Math.abs(pr.exp_margin).toFixed(1)}</dd>
              <dd className="text-xs text-muted">80% range {g.home.team} {signed(pr.distribution.margin_p10_p90[0], 0)} to {signed(pr.distribution.margin_p10_p90[1], 0)}</dd></div>
            <div><dt className="text-xs text-muted">Projected total</dt><dd className="text-[18px]">{num(pr.exp_total, 1)}{pr.exp_total_weather_adj != null && <span className="text-sm text-muted"> ({num(pr.exp_total_weather_adj, 1)} with forecast)</span>}</dd>
              <dd className="text-xs text-muted">80% range {num(pr.distribution.total_p10_p90[0], 0)}–{num(pr.distribution.total_p10_p90[1], 0)}</dd></div>
            <div><dt className="text-xs text-muted">Margin model</dt><dd>{g.home.team} {pct(pr.p_margin_model, 1)}</dd></div>
            <div><dt className="text-xs text-muted">Logistic model</dt><dd>{g.home.team} {pct(pr.p_logit_model, 1)}</dd></div>
            <div><dt className="text-xs text-muted">Elo baseline</dt><dd>{g.home.team} {pct(pr.elo_prob, 1)}</dd></div>
          </dl>
          <p className="text-xs text-muted mt-3">The published probability averages the margin and logistic models. When they disagree, confidence drops.</p>
          <div className="grid sm:grid-cols-2 gap-4 mt-4 text-sm">
            <div><h3 className="font-semibold mb-1">Case for {g.away.team}</h3><ul className="list-disc pl-5 text-muted">{g.factors.away.length ? g.factors.away.map((f) => <li key={f}>{f}</li>) : <li>No factor adds more than 0.25 pts</li>}</ul></div>
            <div><h3 className="font-semibold mb-1">Case for {g.home.team}</h3><ul className="list-disc pl-5 text-muted">{g.factors.home.length ? g.factors.home.map((f) => <li key={f}>{f}</li>) : <li>No factor adds more than 0.25 pts</li>}</ul></div>
          </div>
          {g.factors.risks && <div className="mt-4 text-sm"><h3 className="font-semibold mb-1">What could make this wrong</h3><ul className="list-disc pl-5 text-muted">{g.factors.risks.map((f) => <li key={f}>{f}</li>)}</ul></div>}
          {g.confidence.reasons.length > 0 && <p className="text-xs text-muted mt-3">Confidence is a rules-based label, not a calibrated probability: {g.confidence.reasons.join("; ")}.</p>}
        </Section>

        <Section title="Market and value" aside={<span className="text-xs text-muted">{m ? `${m.source}${m.snapshot ? `, as of ${new Date(m.snapshot).toLocaleString()}` : ""}` : ""}</span>}>
          {!m ? <Note>No market lines for this game yet.</Note> : (
            <>
              <dl className="grid grid-cols-3 gap-3 text-sm tnum mb-3">
                <div><dt className="text-xs text-muted">Moneyline</dt><dd>{g.away.team} {fmtAmerican(m.away_moneyline)}, {g.home.team} {fmtAmerican(m.home_moneyline)}</dd></div>
                <div><dt className="text-xs text-muted">Spread</dt><dd>{m.spread_line != null ? `${g.home.team} ${m.spread_line > 0 ? "-" : "+"}${Math.abs(m.spread_line)}` : "—"}</dd></div>
                <div><dt className="text-xs text-muted">Total</dt><dd>{m.total_line ?? "—"}</dd></div>
                <div><dt className="text-xs text-muted">Book margin</dt><dd>{m.overround != null ? pct(m.overround, 1) : "—"}</dd></div>
                <div><dt className="text-xs text-muted">Model P(cover), {g.home.team}</dt><dd>{pct(pr.distribution.p_home_cover ?? null, 1)}</dd></div>
                <div><dt className="text-xs text-muted">Model P(over)</dt><dd>{pct(pr.distribution.p_over ?? null, 1)}</dd></div>
              </dl>
              <SortTable rows={g.values} cols={vcols} initial="edge" rowKey={(v) => v.selection} />
              <p className="text-xs text-muted mt-2">Highlighted as potential value only when edge ≥ {minEdge.toFixed(1)} pts (your threshold).
                {g.values.filter((v) => v.edge_pp >= minEdge).length ? ` Clears it: ${g.values.filter((v) => v.edge_pp >= minEdge).map((v) => v.selection).join(", ")}.` : " Nothing clears it."} EV = p × (decimal − 1) − (1 − p) per unit. Spread and total probabilities assume a normal margin with SD {num(pr.distribution.margin_sd, 1)} and ignore pushes.</p>
            </>)}
        </Section>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="What drives the margin">
          <ContributionChart rows={pr.contributions} home={g.home.team} away={g.away.team} homeColor={homeC} awayColor={awayC} />
          <p className="text-xs text-muted mt-1">Points of {g.home.team} margin each factor adds, starting from {signed(pr.baseline_margin, 1)} for an even, neutral-site matchup. They sum to the projected margin of {signed(pr.exp_margin, 1)}.</p>
        </Section>
        <Section title="Scoring distribution">
          <MarginHist dist={pr.distribution} home={g.home.team} away={g.away.team} spread={m?.spread_line} />
          <p className="text-xs text-muted mt-1">Probability of each final margin band. Residual SD from training is {num(pr.distribution.margin_sd, 1)} points, which is why a 3-point favourite wins only about 59% of the time.</p>
        </Section>
      </div>

      {(g.scenarios?.length ?? 0) > 0 && (
        <Section title="Alternative scenarios">
          <div className="scroll-x"><table className="grid text-[14px]"><thead><tr><th>Scenario</th><th>Trigger</th><th style={{ textAlign: "right" }}>{g.home.team} win</th><th style={{ textAlign: "right" }}>Margin</th><th style={{ textAlign: "right" }}>Total</th><th style={{ textAlign: "right" }}>Change</th></tr></thead>
            <tbody>
              <tr><td>Base projection</td><td className="text-muted">listed starters play</td><td className="text-right tnum">{pct(pr.p_home, 1)}</td><td className="text-right tnum">{signed(pr.exp_margin)}</td><td className="text-right tnum">{num(pr.exp_total)}</td><td /></tr>
              {g.scenarios!.map((s) => (
                <tr key={s.name}><td>{s.name}</td><td className="text-muted">{s.trigger_status ? `listed: ${s.trigger_status}` : s.kind === "qb" ? "healthy now; shown for reference" : "forecast risk"}</td>
                  <td className="text-right tnum">{pct(s.p_home, 1)}</td><td className="text-right tnum">{signed(s.exp_margin)}</td><td className="text-right tnum">{num(s.exp_total)}</td>
                  <td className="text-right tnum">{s.delta_p_team != null ? `${s.team} ${signed(s.delta_p_team * 100, 1)} pts` : s.delta_total != null ? `total ${signed(s.delta_total, 1)}` : ""}</td></tr>))}
            </tbody></table></div>
          <p className="text-xs text-muted mt-2">QB scenarios rerun the full model with the depth-chart backup's rating (shrunk toward replacement level when he has little history). Other absences are not converted into team win probability; they flow into the touchdown model by reallocating opportunities.</p>
        </Section>)}

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Team comparison" aside={<div className="inline-flex text-sm border border-rule rounded-md overflow-hidden">{(["season", "blended"] as const).map((v) =>
          <button key={v} aria-pressed={statView === v} onClick={() => setStatView(v)} className="px-3 py-1" style={{ background: statView === v ? "var(--raised)" : "transparent" }}>{v === "season" ? "This season" : "Model inputs"}</button>)}</div>}>
          <StatCompare g={g} which={statView} />
          <p className="text-xs text-muted mt-2">{statView === "season" ? "Raw season-to-date numbers before this game." : "What the model uses: this season blended with last season (regressed halfway to league average) so that small samples don't dominate."} The better side is bold.</p>
        </Section>
        <Section title="Recent form">
          <div className="scroll-x"><table className="grid text-[14px]"><thead><tr><th>Window</th><th>Team</th><th style={{ textAlign: "right" }}>Record</th><th style={{ textAlign: "right" }}>Pts for / against</th><th style={{ textAlign: "right" }}>Off EPA</th><th style={{ textAlign: "right" }}>Def EPA allowed</th></tr></thead>
            <tbody>{(["last3", "last5", "last10"] as const).flatMap((w) => (["away", "home"] as const).map((side) => {
              const f = g[side].form?.[w];
              return f ? <tr key={w + side}><td className="text-muted">{w.replace("last", "Last ")}{f.spans_prior_season ? "*" : ""}</td><td>{g[side].team}</td><td className="text-right tnum">{f.record}</td>
                <td className="text-right tnum">{f.points_pg.toFixed(1)} / {f.points_allowed_pg.toFixed(1)}</td><td className="text-right tnum">{f.epa_play.toFixed(3)}</td><td className="text-right tnum">{f.def_epa_play.toFixed(3)}</td></tr> : null;
            }))}</tbody></table></div>
          <p className="text-xs text-muted mt-2">* includes games from last season. Form is shown for context. The model weights it through the season blend rather than chasing streaks.</p>
          {g.h2h && g.h2h.length > 0 && <>
            <h3 className="font-semibold text-sm mt-4 mb-1">Head to head</h3>
            <div className="scroll-x"><table className="grid text-[13.5px]"><thead><tr><th>Season</th><th>Result</th><th>QBs</th><th>Relevance today</th></tr></thead>
              <tbody>{g.h2h.map((h) => <tr key={h.game_id}><td className="tnum">{h.season} wk {h.week}</td><td className="tnum">{h.away} {h.away_score} @ {h.home} {h.home_score}</td>
                <td className="text-muted">{h.away_qb} vs {h.home_qb}</td><td className="text-muted">{h.relevance} ({h.same_qbs}/2 same QBs, {h.same_coaches}/2 same coaches)</td></tr>)}</tbody></table></div>
            <p className="text-xs text-muted mt-2">Head-to-head history is context only and is not a model input. Meetings with different quarterbacks or coaches say little about this one.</p>
          </>}
        </Section>
      </div>

      {g.matchups && (
        <Section title="Offense vs defense matchups">
          <div className="grid lg:grid-cols-2 gap-5">
            <div><h3 className="text-sm font-semibold mb-2">{g.away.team} offense vs {g.home.team} defense</h3><MatchupTable rows={g.matchups.away_off} off={g.away.team} def={g.home.team} /></div>
            <div><h3 className="text-sm font-semibold mb-2">{g.home.team} offense vs {g.away.team} defense</h3><MatchupTable rows={g.matchups.home_off} off={g.home.team} def={g.away.team} /></div>
          </div>
          <p className="text-xs text-muted mt-3">{g.matchups.note} Ranks are 1 = best for that unit. Tendencies: {g.away.team} play-action {pct(g.matchups.away_extras.off_pa_rate)}, {g.home.team} blitz {pct(g.matchups.away_extras.def_blitz_rate)}; {g.home.team} play-action {pct(g.matchups.home_extras.off_pa_rate)}, {g.away.team} blitz {pct(g.matchups.home_extras.def_blitz_rate)}.
            Not available in free data: {g.matchups.unavailable.join(", ")}.</p>
        </Section>)}

      <div className="grid lg:grid-cols-3 gap-5">
        {(["away", "home"] as const).map((side) => (
          <Section key={side} title={`${g[side].team} injury report`}><InjuryList s={g[side]} />
            {g.td_ruled_out?.filter((x) => x.team === g[side].team).length ? <p className="text-xs text-muted mt-2">Ruled out and removed from TD projections: {g.td_ruled_out.filter((x) => x.team === g[side].team).map((x) => x.name).join(", ")}.</p> : null}
          </Section>))}
        <Section title="Weather and venue"><WeatherCard w={g.weather} g={g} />
          {alerts.filter((a) => a.kind === "weather").length > 0 && <p className="text-sm mt-2" style={{ color: "var(--warn)" }}>{alerts.filter((a) => a.kind === "weather").map((a) => a.text).join(". ")}</p>}
          <p className="text-xs text-muted mt-2">Travel: {g.away.team} {Math.round(g.away.travel_km)} km ({signed(g.away.tz_shift, 0)} h time zones), {g.home.team} {Math.round(g.home.travel_km)} km. Rest: {g.away.team} {g.away.rest_days} days, {g.home.team} {g.home.rest_days} days.</p>
        </Section>
      </div>

      <Section title="Anytime touchdown scorers" aside={<Toggle on={withoutUncertain} set={setWithoutUncertain} label="Questionable players sit" />}>
        {td.length ? <TDTable rows={td} teams={T} showGame={false} /> : <Note>No touchdown projections for this game. They're produced for the current week only.</Note>}
      </Section>

      {(g.history?.length ?? 0) > 1 && (
        <Section title="How the projection has moved"><HistoryChart rows={g.history!} />
          <p className="text-xs text-muted">Each point is a logged pipeline run before kickoff. These rows are append-only.</p></Section>)}

      <Section title="Inspect the inputs" aside={<button className="text-sm link" onClick={() => setShowRaw(!showRaw)} aria-expanded={showRaw}>{showRaw ? "Hide" : "Show"} raw values</button>}>
        <Note>Every input behind this projection, as computed before kickoff. Margin contributions are in points; total contributions are relative to an average game ({num(pr.baseline_total, 1)} points).</Note>
        {showRaw && (
          <div className="grid md:grid-cols-2 gap-5 mt-3 text-[13px]">
            <table className="grid"><thead><tr><th>Margin feature</th><th style={{ textAlign: "right" }}>Value</th><th style={{ textAlign: "right" }}>Pts</th></tr></thead>
              <tbody>{pr.contributions.map((c) => <tr key={c.feature}><td>{c.label}</td><td className="text-right tnum">{c.value.toFixed(3)}</td><td className="text-right tnum">{signed(c.points, 2)}</td></tr>)}</tbody></table>
            <table className="grid"><thead><tr><th>Total feature</th><th style={{ textAlign: "right" }}>Value</th><th style={{ textAlign: "right" }}>Pts</th></tr></thead>
              <tbody>{pr.total_contributions.map((c) => <tr key={c.feature}><td>{c.label}</td><td className="text-right tnum">{c.value.toFixed(3)}</td><td className="text-right tnum">{signed(c.points, 2)}</td></tr>)}</tbody></table>
          </div>)}
      </Section>
    </div>
  );
}
