import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useApp } from "../App";
import MatchupCard from "../components/MatchupCard";
import { EdgeSlider, Note, ProbViewToggle, Section, TeamMark } from "../components/ui";
import { alertsFor, isUncertainGame, label, shownProbs, tdP, valuesAbove } from "../lib/derive";
import { ago, kickoffLocal, pct, slotOf } from "../lib/format";
import { fmtAmerican } from "../lib/odds";
import { useSettings } from "../lib/store";
import { usePerformance } from "../lib/data";

type SortKey = "kickoff" | "winprob" | "spread" | "edge";

export default function Slate() {
  const { meta, week, ref } = useApp();
  const { minEdge, probView, withoutUncertain } = useSettings();
  const { search } = useLocation();
  const perf = usePerformance();
  const [slot, setSlot] = useState("All");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("kickoff");
  const games = week!.games;
  const slots = ["All", ...new Set(games.map(slotOf))];

  const shown = useMemo(() => {
    let g = games.filter((x) => slot === "All" || slotOf(x) === slot);
    if (q.trim()) {
      const s = q.trim().toLowerCase();
      g = g.filter((x) => [x.home.team, x.away.team, meta.teams[x.home.team]?.name, meta.teams[x.away.team]?.name, x.home.qb.name, x.away.qb.name]
        .some((v) => v?.toLowerCase().includes(s)));
    }
    const fav = (x: typeof g[number]) => Math.max(shownProbs(x, probView).pHome, 1 - shownProbs(x, probView).pHome);
    const best = (x: typeof g[number]) => Math.max(-99, ...(x.values ?? []).map((v) => v.edge_pp));
    const by: Record<SortKey, (a: typeof g[number], b: typeof g[number]) => number> = {
      kickoff: (a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc),
      winprob: (a, b) => fav(b) - fav(a),
      spread: (a, b) => Math.abs(b.prediction.exp_margin) - Math.abs(a.prediction.exp_margin),
      edge: (a, b) => best(b) - best(a),
    };
    return [...g].sort(by[sort]);
  }, [games, slot, q, sort, probView, meta.teams]);

  const upcoming = games.filter((g) => !g.result);
  const teamsRank = games.flatMap((g) => {
    const p = shownProbs(g, probView).pHome;
    return [{ team: g.home.team, opp: g.away.team, p, g }, { team: g.away.team, opp: g.home.team, p: 1 - p, g }];
  }).sort((a, b) => b.p - a.p);
  const tdLive = week!.td.filter((t) => !t.backtest);
  const tdList = (tdLive.length ? tdLive : week!.td).map((t) => ({ t, p: tdP(t, withoutUncertain) })).filter((x) => x.p != null)
    .sort((a, b) => b.p! - a.p!);
  const allValues = upcoming.flatMap((g) => valuesAbove(g, minEdge).map((v) => ({ v, g }))).sort((a, b) => b.v.edge_pp - a.v.edge_pp);
  const alerts = upcoming.flatMap(alertsFor).sort((a, b) => b.severity - a.severity);
  const uncertain = upcoming.filter(isUncertainGame).length;
  const isPast = ref.kind === "past";

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="display text-[30px] leading-tight">{ref.season} {ref.label}</h1>
          <p className="text-muted text-sm">
            {isPast ? "Completed week. Predictions shown are walk-forward backtests made with data available before each game."
              : ref.kind === "lookahead" ? "Early look. Team projections only; injuries, weather and lines will move."
              : "Pre-kickoff projections, refreshed several times a day."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4"><ProbViewToggle /><EdgeSlider /></div>
      </div>

      <dl className="grid grid-cols-2 md:grid-cols-5 gap-px rounded-[10px] overflow-hidden border border-rule bg-[var(--rule)]">
        {[
          ["Games analysed", String(games.length), `${upcoming.length} still to play`],
          ["Highest win probability", teamsRank[0] ? pct(teamsRank[0].p) : "—", teamsRank[0] ? `${teamsRank[0].team} vs ${teamsRank[0].opp}` : ""],
          ["Highest anytime TD", tdList[0] ? pct(tdList[0].p) : "—", tdList[0] ? `${tdList[0].t.name}, ${tdList[0].t.team}` : "No TD projections this week"],
          ["Potential value spots", String(allValues.length), `edge ≥ ${minEdge.toFixed(1)} pts vs no-vig market`],
          ["Games with big unknowns", String(uncertain), "QB, injury or weather uncertainty"],
        ].map(([k, v, s], i) => (
          <div key={k} className={`bg-panel p-4 ${i === 4 ? "col-span-2 md:col-span-1" : ""}`}>
            <dt className="text-xs text-muted">{k}</dt>
            <dd className="display text-[28px] tnum leading-tight mt-1">{v}</dd>
            <dd className="text-xs text-muted truncate">{s}</dd>
          </div>
        ))}
      </dl>

      <div className="grid lg:grid-cols-[1fr_380px] gap-5 items-start">
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1" role="group" aria-label="Kickoff window">
              {slots.map((s) => (
                <button key={s} onClick={() => setSlot(s)} aria-pressed={slot === s}
                  className={`px-3 py-1 rounded-full text-sm border ${slot === s ? "border-[var(--model)] text-fg" : "border-rule text-muted"}`}>{s}</button>
              ))}
            </div>
            <input type="search" placeholder="Team or QB" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter games by team or quarterback" className="w-40" />
            <label className="text-sm text-muted flex items-center gap-2">Sort
              <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                <option value="kickoff">Kickoff</option><option value="winprob">Biggest favourite</option>
                <option value="spread">Projected margin</option><option value="edge">Best edge</option>
              </select>
            </label>
          </div>
          {shown.length === 0 ? <div className="panel p-6 text-muted">No games match. Clear the search or pick another window.</div> : (
            <div className="grid md:grid-cols-2 gap-4">{shown.map((g) => <MatchupCard key={g.game_id} g={g} teams={meta.teams} />)}</div>
          )}
        </div>

        <aside className="grid gap-4">
          <Section title="Potential value" aside={<Link to={{ pathname: "/value", search }} className="link text-sm">All markets</Link>}>
            {isPast ? <Note>Value flags are only shown for games that haven't kicked off.</Note> : allValues.length === 0 ? <Note>No market clears a {minEdge.toFixed(1)}-point edge. Lower the threshold to see closer calls.</Note> : (
              <ul className="grid gap-2">
                {allValues.slice(0, 6).map(({ v, g }) => (
                  <li key={g.game_id + v.selection}>
                    <Link to={{ pathname: `/game/${g.game_id}`, search }} className="flex items-baseline justify-between gap-3 text-sm hover:underline">
                      <span><span className="font-semibold">{v.selection}</span> <span className="text-muted">{fmtAmerican(v.odds)}, {label(g)}</span></span>
                      <span className="tnum" style={{ color: "var(--pos)" }}>+{v.edge_pp.toFixed(1)}</span>
                    </Link>
                    <div className="text-xs text-muted tnum">model {pct(v.model_p, 1)} vs market {pct(v.no_vig, 1)}, EV {v.ev_per_unit >= 0 ? "+" : ""}{v.ev_per_unit.toFixed(3)}/unit</div>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted mt-3">An edge can come from model error or news the model hasn't seen. The market has been the more accurate forecaster in backtests.</p>
          </Section>

          <Section title="Anytime TD leaders" aside={<Link to={{ pathname: "/touchdowns", search }} className="link text-sm">Full rankings</Link>}>
            {tdList.length === 0 ? <Note>No touchdown projections for this week.</Note> : (
              <ol className="grid gap-1.5">
                {tdList.slice(0, 10).map(({ t, p }) => (
                  <li key={t.player_id + t.game_id} className="flex items-center gap-2 text-sm">
                    <TeamMark team={t.team} info={meta.teams[t.team]} size={18} />
                    <span className="flex-1 truncate">{t.name} <span className="text-muted text-xs">{t.position}, vs {t.opp}</span></span>
                    {t.scored != null && <span className="text-xs" style={{ color: t.scored ? "var(--pos)" : "var(--muted)" }}>{t.scored ? "scored" : "no TD"}</span>}
                    {t.confidence?.score != null && <span className="tnum text-xs text-muted w-9 text-right" title="Score out of 10">{t.confidence.score}/10</span>}
                    <span className="tnum font-semibold w-12 text-right">{pct(p)}</span>
                  </li>
                ))}
              </ol>
            )}
          </Section>

          <Section title="Win probability ranking">
            <ol className="grid gap-1">
              {teamsRank.slice(0, 32).map((r) => (
                <li key={r.team} className="flex items-center gap-2 text-sm">
                  <TeamMark team={r.team} info={meta.teams[r.team]} size={16} />
                  <span className="w-10 font-semibold">{r.team}</span>
                  <span className="text-xs text-muted w-14">vs {r.opp}</span>
                  <span className="flex-1 h-1.5 rounded-full bg-[var(--raised)] overflow-hidden">
                    <span className="block h-full fill-in" style={{ width: `${r.p * 100}%`, background: probView === "model" ? "var(--model)" : "var(--market)" }} />
                  </span>
                  <span className="tnum w-10 text-right">{pct(r.p)}</span>
                </li>
              ))}
            </ol>
          </Section>

          <Section title="Injury and weather alerts">
            {alerts.length === 0 ? <Note>{isPast ? "Alerts apply to upcoming games." : "No designated injuries at key positions and no weather flags yet."}</Note> : (
              <ul className="grid gap-1.5 text-sm max-h-[340px] overflow-auto pr-1">
                {alerts.slice(0, 40).map((a, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1.5 inline-block w-1.5 h-1.5 rounded-full shrink-0" style={{ background: a.severity === 2 ? "var(--warn)" : "var(--muted)" }} />
                    <Link to={{ pathname: `/game/${a.game.game_id}`, search }} className="hover:underline">{a.text}</Link>
                  </li>
                ))}
              </ul>
            )}
            {!meta.weather_enabled && <p className="text-xs text-muted mt-2">Weather forecasts were not fetched in this build.</p>}
          </Section>

          <Section title="Model track record" aside={<Link to={{ pathname: "/performance", search }} className="link text-sm">Details</Link>}>
            {perf.data ? (
              <div className="text-sm grid gap-2">
                <p className="text-muted text-[13px]">Out-of-sample backtest, {perf.data.game.period}</p>
                <div className="grid grid-cols-3 gap-2 tnum">
                  {[["Model", perf.data.game.overall.model], ["Elo baseline", perf.data.game.overall.elo], ["Market", perf.data.game.overall.market]].map(([n, s]) => (
                    <div key={n as string} className="subpanel p-2">
                      <div className="text-xs text-muted">{n as string}</div>
                      <div className="font-semibold">{pct((s as { accuracy: number }).accuracy, 1)}</div>
                      <div className="text-xs text-muted">log loss {(s as { log_loss: number }).log_loss.toFixed(3)}</div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted">Pre-kickoff log: {perf.data.prospective.games_logged} games logged, {perf.data.prospective.games_graded} graded so far.</p>
              </div>
            ) : <Note>Loading…</Note>}
          </Section>

          <Section title="Data freshness" aside={<Link to={{ pathname: "/data", search }} className="link text-sm">Sources</Link>}>
            <ul className="text-[13px] grid gap-1">
              {["games.csv", `play_by_play_${meta.season}.parquet`, `injuries_${meta.season}.csv`, `snap_counts_${meta.season}.csv`, `roster_weekly_${meta.season}.csv`].map((f) => {
                const s = meta.sources.find((x) => x.file === f);
                return <li key={f} className="flex justify-between gap-2"><span className="text-muted">{FRIENDLY[f.replace(/_?\d{4}/, "")] ?? f}</span><span>{s ? ago(s.source_updated) : "not loaded"}</span></li>;
              })}
              <li className="flex justify-between gap-2"><span className="text-muted">Odds</span><span>{meta.odds_source === "the-odds-api" ? "live API" : "nflverse consensus"}</span></li>
            </ul>
            <p className="text-xs text-muted mt-2">Kickoff times are shown in your time zone. First game: {games[0] ? kickoffLocal(games[0].kickoff_utc).day : "—"}.</p>
          </Section>
        </aside>
      </div>
    </div>
  );
}

const FRIENDLY: Record<string, string> = {
  "games.csv": "Schedule, scores, lines", "play_by_play.parquet": "Play-by-play", "injuries.csv": "Injury report",
  "snap_counts.csv": "Snap counts", "roster_weekly.csv": "Rosters",
};
