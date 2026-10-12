import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApp } from "../App";
import { EdgeSlider, ErrorBox, Loading, Note, Section, SortTable, Toggle, type Col } from "../components/ui";
import { usePicks } from "../lib/data";
import { pct, units } from "../lib/format";
import { fmtAmerican, probToAmerican } from "../lib/odds";
import { useSettings } from "../lib/store";
import type { GamePick, TDPick } from "../types";

const RES_COLOR = { won: "var(--pos)", lost: "var(--neg)", push: "var(--muted)", void: "var(--muted)", pending: "var(--muted)" } as const;
const RES_TEXT = { won: "Won", lost: "Lost", push: "Push", void: "Void", pending: "Pending" } as const;
const MKT = { moneyline: "Moneyline", spread: "Spread", total: "Total" } as const;
const wkKey = (s: number, w: number) => `${s}_${String(w).padStart(2, "0")}`;

function record(rows: { result: string }[]) {
  const w = rows.filter((r) => r.result === "won").length, l = rows.filter((r) => r.result === "lost").length;
  const p = rows.filter((r) => r.result === "push").length;
  return { w, l, p, text: `${w}-${l}${p ? `-${p}` : ""}`, rate: w + l ? w / (w + l) : null };
}

export default function PicksPage() {
  const { meta } = useApp();
  const { data, error } = usePicks();
  const { minEdge } = useSettings();
  const [week, setWeek] = useState("All");
  const [market, setMarket] = useState("All");
  const [minScore, setMinScore] = useState(9);
  const [raw, setRaw] = useState(false);
  if (error) return <ErrorBox msg={error} />;
  if (!data) return <Loading />;
  const weeks = [...new Set([...data.game, ...data.td].map((r) => wkKey(r.season, r.week)))].sort().reverse();
  const inWeek = (r: { season: number; week: number }) => week === "All" || wkKey(r.season, r.week) === week;
  const edgeOf = (r: GamePick) => (raw ? r.edge_pp : r.anchored_edge_pp);
  const evOf = (r: GamePick) => (raw ? r.ev : r.anchored_ev);
  const games = data.game.filter((r) => inWeek(r) && evOf(r) > 0 && edgeOf(r) >= minEdge && (market === "All" || r.market === market));
  const settled = games.filter((r) => r.result !== "pending");
  const staked = settled.filter((r) => r.result !== "push").length;
  const pl = settled.reduce((a, r) => a + r.profit, 0);
  const tds = data.td.filter((r) => inWeek(r) && r.score >= minScore);
  const tdSettled = tds.filter((r) => r.result === "won" || r.result === "lost");
  const tdHit = tdSettled.length ? tdSettled.filter((r) => r.result === "won").length / tdSettled.length : null;
  const tdExp = tdSettled.length ? tdSettled.reduce((a, r) => a + r.p, 0) / tdSettled.length : null;

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">Pick history</h1>
        <p className="text-muted text-sm max-w-[80ch]">Every pick the model logged before kickoff, graded against the result. Game picks are sides with positive expected value at the logged price, using the market-anchored probability by default. Anchoring is fit only on seasons before each pick, so it isn't hindsight. Switch on raw model edges to see what the unanchored model would have bet. TD picks are its top-scored players. Losing picks stay in the record. Nothing is removed after the fact.</p>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <select id="picks-week" value={week} onChange={(e) => setWeek(e.target.value)} aria-label="Week">
          <option value="All">All weeks</option>
          {weeks.map((w) => <option key={w} value={w}>{w.slice(0, 4)} week {Number(w.slice(5))}</option>)}
        </select>
        <select id="picks-market" value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Market">
          <option value="All">All game markets</option><option value="moneyline">Moneyline</option><option value="spread">Spread</option><option value="total">Total</option>
        </select>
        <EdgeSlider />
        <Toggle on={raw} set={setRaw} label="Use raw model edges" />
        <label className="flex items-center gap-2"><span className="text-muted">TD picks at</span>
          <select id="picks-score" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} aria-label="Minimum TD score">
            {[10, 9, 8, 7, 6].map((s) => <option key={s} value={s}>{s}+/10</option>)}
          </select></label>
      </div>

      <dl className="grid grid-cols-2 md:grid-cols-4 gap-px rounded-[10px] overflow-hidden border border-rule bg-[var(--rule)]">
        {[
          ["Game picks", record(settled).text, `${games.length - settled.length} pending, edge ≥ ${minEdge.toFixed(1)} pts`],
          ["Profit (1 unit each)", units(pl), staked ? `ROI ${((pl / staked) * 100).toFixed(1)}% on ${staked} bets` : "no settled bets"],
          ["TD picks scored", tdHit == null ? "—" : pct(tdHit), tdExp == null ? "none settled" : `${tdSettled.filter((r) => r.result === "won").length} of ${tdSettled.length}, model expected ${pct(tdExp)}`],
          ["TD picks pending or void", String(tds.length - tdSettled.length), "void = no touches (didn't play)"],
        ].map(([k, v, s]) => (
          <div key={k} className="bg-panel p-4"><dt className="text-xs text-muted">{k}</dt><dd className="display text-[26px] tnum mt-1">{v}</dd><dd className="text-xs text-muted">{s}</dd></div>))}
      </dl>

      <div className="grid lg:grid-cols-[1fr_360px] gap-5 items-start">
        <Section title="Running profit">
          {settled.length < 2 ? <Note>The chart appears once at least two picks have settled.</Note> : <ProfitChart rows={settled} />}
          <p className="text-xs text-muted mt-1">Cumulative units from flat 1-unit bets on every game pick shown, in kickoff order.</p>
        </Section>
        <Section title="By market">
          <table className="dtable text-[14px]"><thead><tr><th>Market</th><th style={{ textAlign: "right" }}>Record</th><th style={{ textAlign: "right" }}>Units</th></tr></thead>
            <tbody>{(["moneyline", "spread", "total"] as const).map((m) => {
              const rs = settled.filter((r) => r.market === m), u = rs.reduce((a, r) => a + r.profit, 0);
              return <tr key={m}><td>{MKT[m]}</td><td className="text-right tnum">{record(rs).text}</td><td className="text-right tnum" style={{ color: u > 0 ? "var(--pos)" : u < 0 ? "var(--neg)" : undefined }}>{units(u)}</td></tr>;
            })}</tbody></table>
          <p className="text-xs text-muted mt-2">In backtests, flat-betting these edges at closing prices lost money, so a hot or cold week says little either way.</p>
        </Section>
      </div>

      <Section title={`Game picks (${games.length})`}>
        <SortTable<GamePick> rows={games} initial="ko" desc={false} rowKey={(r) => r.game_id + r.selection} empty={raw ? `No picks clear a ${minEdge.toFixed(1)}-pt edge for this filter.` : `No market-anchored picks clear a ${minEdge.toFixed(1)}-pt edge. That is expected: in backtests the model's disagreements with the market carried almost no information, so anchoring leaves few or no bets. Toggle raw model edges to see what it would have bet.`} cols={[
          { key: "ko", label: "Game", sort: (r) => r.kickoff_utc, render: (r) => <Link className="hover:underline" to={{ pathname: `/game/${r.game_id}`, search: `?w=${wkKey(r.season, r.week)}` }}>{r.matchup}<div className="text-xs text-muted">wk {r.week}</div></Link> },
          { key: "mkt", label: "Market", sort: (r) => r.market, render: (r) => <span className="text-muted">{MKT[r.market]}</span> },
          { key: "sel", label: "Pick", sort: (r) => r.selection, render: (r) => <span className="font-medium">{r.selection}</span> },
          { key: "odds", label: "Price", align: "right", sort: (r) => r.odds, render: (r) => <span title={`Price source: ${r.price_source}`}>{fmtAmerican(r.odds)}{r.price_source !== "logged" ? "*" : ""}</span> },
          { key: "p", label: "Model", align: "right", sort: (r) => r.model_p, render: (r) => <span style={{ color: "var(--model)" }}>{pct(r.model_p, 1)}</span> },
          { key: "nv", label: "Market", align: "right", sort: (r) => r.no_vig, render: (r) => <span style={{ color: "var(--market)" }}>{pct(r.no_vig, 1)}</span> },
          { key: "anc", label: "Anchored", align: "right", sort: (r) => r.anchored_p, render: (r) => pct(r.anchored_p, 1) },
          { key: "edge", label: raw ? "Raw edge" : "Edge", align: "right", sort: edgeOf, render: (r) => `${edgeOf(r) >= 0 ? "+" : ""}${edgeOf(r).toFixed(1)}` },
          { key: "ev", label: "EV / $1", align: "right", sort: evOf, render: (r) => `${evOf(r) >= 0 ? "+" : ""}${(evOf(r) * 100).toFixed(0)}¢` },
          { key: "res", label: "Result", sort: (r) => r.result, render: (r) => <span style={{ color: RES_COLOR[r.result] }}>{RES_TEXT[r.result]}{r.final ? <span className="text-xs text-muted"> {r.final}</span> : null}</span> },
          { key: "pl", label: "Units", align: "right", sort: (r) => r.profit, render: (r) => r.result === "pending" ? "—" : <span style={{ color: r.profit > 0 ? "var(--pos)" : r.profit < 0 ? "var(--neg)" : undefined }}>{units(r.profit)}</span> },
        ]} />
        <p className="text-xs text-muted mt-2">Each pick uses the last projection logged before kickoff. * Prices for picks logged before Oct 12 come from the consensus line in the schedule data, because those early logs stored moneylines only. Later picks use the exact price the model evaluated.</p>
      </Section>

      <Section title={`TD picks scored ${minScore}+/10 (${tds.length})`}>
        <SortTable<TDPick> rows={tds} initial="p" rowKey={(r) => r.game_id + r.player_id} empty="No TD picks at this score for this filter." cols={[
          { key: "name", label: "Player", sort: (r) => r.name, render: (r) => <span><span className="font-medium">{r.name}</span> <span className="text-xs text-muted">{r.position}, {r.team}</span></span> },
          { key: "wk", label: "Week", sort: (r) => r.kickoff_utc, render: (r) => <span className="text-muted">{r.week}</span> },
          { key: "p", label: "Anytime TD", align: "right", sort: (r) => r.p, render: (r) => pct(r.p, 1) },
          { key: "score", label: "Score", align: "right", sort: (r) => r.score, render: (r) => `${r.score}/10` },
          { key: "fair", label: "Fair odds", align: "right", sort: (r) => r.p, render: (r) => fmtAmerican(probToAmerican(Math.min(0.99, r.p))) },
          { key: "res", label: "Result", sort: (r) => r.result, render: (r) => <span style={{ color: RES_COLOR[r.result] }}>{r.result === "void" ? "Void (no touches)" : RES_TEXT[r.result]}</span> },
        ]} />
        <p className="text-xs text-muted mt-2">{meta.td_market_available ? "Profit uses the logged sportsbook price." : "No sportsbook TD prices are connected, so TD picks are graded on hit rate only. To profit, a pick needs a book price longer than its fair odds."}</p>
      </Section>
    </div>
  );
}

function ProfitChart({ rows }: { rows: GamePick[] }) {
  const data = useMemo(() => {
    let c = 0;
    return [...rows].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc)).map((r, i) => ({ i: i + 1, u: +(c += r.profit).toFixed(2), label: `${r.selection} (${r.matchup})` }));
  }, [rows]);
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid stroke="#24344f" vertical={false} />
        <XAxis dataKey="i" stroke="#8a9bb5" fontSize={12} tickLine={false} />
        <YAxis stroke="#8a9bb5" fontSize={12} tickLine={false} width={40} />
        <ReferenceLine y={0} stroke="#8a9bb5" />
        <Tooltip contentStyle={{ background: "#1b2b45", border: "1px solid #24344f", borderRadius: 8, color: "#e6ecf5", fontSize: 13 }}
          labelFormatter={(_, p) => p?.[0]?.payload?.label ?? ""} formatter={(v: number) => [`${v > 0 ? "+" : ""}${v}u`, "Running total"]} />
        <Line dataKey="u" stroke="#5ab4ff" strokeWidth={2} dot={{ r: 2 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
