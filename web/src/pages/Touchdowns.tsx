import { useMemo, useState } from "react";
import { useApp } from "../App";
import TDTable, { tdExportRows } from "../components/TDTable";
import { Note, Section, Toggle } from "../components/ui";
import { label, tdP } from "../lib/derive";
import { EXPORT_LABEL, exportCSV } from "../lib/csv";
import { useSettings } from "../lib/store";

export default function Touchdowns() {
  const { meta, week, ref } = useApp();
  const { withoutUncertain, setWithoutUncertain } = useSettings();
  const [team, setTeam] = useState("All");
  const [game, setGame] = useState("All");
  const [pos, setPos] = useState("All");
  const [minP, setMinP] = useState(5);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const all = week!.td;
  const games = week!.games;
  const teams = [...new Set(all.map((t) => t.team))].sort();
  const rows = useMemo(() => all.filter((t) => (team === "All" || t.team === team) && (game === "All" || t.game_id === game)
    && (pos === "All" || t.position === pos) && (q === "" || t.name.toLowerCase().includes(q.toLowerCase()))
    && ((tdP(t, withoutUncertain) ?? t.p) * 100 >= minP)), [all, team, game, pos, minP, q, withoutUncertain]);
  const isBacktest = all.length > 0 && all.every((t) => t.backtest);

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">Anytime touchdown scorers</h1>
        <p className="text-muted text-sm max-w-[80ch]">
          Probability that a player scores at least one rushing or receiving touchdown. That's the anytime market, not first-TD,
          and passing TDs don't count for quarterbacks. The model ranks by projected opportunity (carries by field zone, red-zone and
          end-zone targets), team scoring expectation, game script and opponent, not by past TD totals.
        </p>
      </div>
      <Section title={`${ref.season} ${ref.label}: ${rows.length} players`} aside={
        <div className="flex flex-wrap gap-3 items-center">
          <Toggle on={withoutUncertain} set={setWithoutUncertain} label="Questionable players sit" />
          <button className="text-sm px-3 py-1 rounded-md border border-rule hover:border-[var(--muted)]"
            onClick={async () => setMsg(await exportCSV(`anytime_td_${ref.season}_wk${ref.week}.csv`, tdExportRows(rows, withoutUncertain)))}>{msg || EXPORT_LABEL}</button>
        </div>}>
        <div className="flex flex-wrap gap-3 mb-4 items-center text-sm">
          <input type="search" placeholder="Player" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search players" className="w-40" />
          <select value={game} onChange={(e) => setGame(e.target.value)} aria-label="Game">
            <option value="All">All games</option>
            {games.map((g) => <option key={g.game_id} value={g.game_id}>{label(g)}</option>)}
          </select>
          <select value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Team">
            <option value="All">All teams</option>{teams.map((t) => <option key={t}>{t}</option>)}
          </select>
          <select value={pos} onChange={(e) => setPos(e.target.value)} aria-label="Position">
            <option value="All">All positions</option>{["RB", "WR", "TE", "QB"].map((p) => <option key={p}>{p}</option>)}
          </select>
          <label className="flex items-center gap-2"><span className="text-muted">At least</span>
            <input type="range" min={0} max={50} step={1} value={minP} onChange={(e) => setMinP(+e.target.value)} aria-label="Minimum probability" />
            <span className="tnum w-10">{minP}%</span></label>
        </div>
        {isBacktest && <div className="mb-3"><Note>This is a completed week. Probabilities are walk-forward backtests, and the population is players who actually took a snap.</Note></div>}
        {!meta.td_market_available && !isBacktest && <div className="mb-3"><Note>Sportsbook anytime-TD prices aren't connected (they need a paid odds plan), so edge and EV columns are hidden. Fair odds show the price at which a bet breaks even if the model is right.</Note></div>}
        <TDTable rows={rows} teams={meta.teams} />
        <p className="text-xs text-muted mt-3">Click a row to see the opportunity breakdown, recent touchdowns, usage and what drives the number. With the toggle on, questionable and doubtful players are removed and their opportunities are reallocated to teammates.</p>
      </Section>
    </div>
  );
}
