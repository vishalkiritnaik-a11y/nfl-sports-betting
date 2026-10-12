import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useApp } from "../App";
import { Edge, EdgeSlider, Note, Section, SortTable, Toggle, type Col } from "../components/ui";
import { label } from "../lib/derive";
import { EXPORT_LABEL, exportCSV } from "../lib/csv";
import { pct } from "../lib/format";
import { fmtAmerican } from "../lib/odds";
import { useSettings } from "../lib/store";
import type { Game, ValueRow } from "../types";

type Row = ValueRow & { g: Game };

export default function Value() {
  const { meta, week, ref } = useApp();
  const { minEdge } = useSettings();
  const [msg, setMsg] = useState("");
  const { search } = useLocation();
  const [market, setMarket] = useState("All");
  const [onlyFlagged, setOnlyFlagged] = useState(true);
  const [team, setTeam] = useState("All");
  const rows: Row[] = useMemo(() => week!.games.filter((g) => !g.result).flatMap((g) => g.values.map((v) => ({ ...v, g }))), [week]);
  const shown = rows.filter((r) => (market === "All" || r.market === market) && (!onlyFlagged || r.edge_pp >= minEdge)
    && (team === "All" || r.g.home.team === team || r.g.away.team === team));
  const teams = [...new Set(week!.games.flatMap((g) => [g.home.team, g.away.team]))].sort();
  const cols: Col<Row>[] = [
    { key: "game", label: "Game", sort: (r) => r.g.kickoff_utc, render: (r) => <Link className="hover:underline" to={{ pathname: `/game/${r.g.game_id}`, search }}>{label(r.g)}</Link> },
    { key: "mkt", label: "Market", sort: (r) => r.market, render: (r) => <span className="text-muted">{r.market}</span> },
    { key: "sel", label: "Selection", sort: (r) => r.selection, render: (r) => <span className="font-medium">{r.selection}</span> },
    { key: "odds", label: "Price", align: "right", sort: (r) => r.odds, render: (r) => fmtAmerican(r.odds) },
    { key: "model", label: "Model", align: "right", sort: (r) => r.model_p, render: (r) => <span style={{ color: "var(--model)" }}>{pct(r.model_p, 1)}</span> },
    { key: "anc", label: "Anchored", align: "right", title: "Model probability shrunk toward the market by as much as backtests say the model deserves", sort: (r) => r.anchored_p ?? null, render: (r) => pct(r.anchored_p ?? null, 1) },
    { key: "nv", label: "No-vig", align: "right", sort: (r) => r.no_vig, render: (r) => <span style={{ color: "var(--market)" }}>{pct(r.no_vig, 1)}</span> },
    { key: "redge", label: "Raw edge", align: "right", sort: (r) => r.raw_edge_pp ?? null, render: (r) => <span className="text-muted">{r.raw_edge_pp != null ? `${r.raw_edge_pp > 0 ? "+" : ""}${r.raw_edge_pp.toFixed(1)}` : "—"}</span> },
    { key: "edge", label: "Edge (pts)", align: "right", sort: (r) => r.edge_pp, render: (r) => <Edge v={r.edge_pp} /> },
    { key: "ev", label: "EV / unit", align: "right", sort: (r) => r.ev_per_unit, render: (r) => <Edge v={r.ev_per_unit} /> },
    { key: "roi", label: "ROI %", align: "right", sort: (r) => r.roi_pct, render: (r) => <Edge v={r.roi_pct} /> },
    { key: "conf", label: "Game confidence", sort: (r) => ({ High: 3, Medium: 2, Low: 1, "n/a": 0 })[r.g.confidence.label], render: (r) => <span className="text-muted">{r.g.confidence.label}</span> },
  ];
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">Value finder</h1>
        <p className="text-muted text-sm max-w-[80ch]">Where the model's view differs from the market's, after correcting for how often that disagreement has actually paid off. Backtests showed results track the closing line, not the raw model, so edges use a market-anchored probability: the model shrunk toward the market by the amount history supports. Raw edges are shown for reference only. The market probability has the bookmaker's margin removed
          proportionally, so the two sides sum to 100%. A spot is flagged only when the model beats it by your minimum edge.</p>
      </div>
      <Section title={`${ref.season} ${ref.label}: ${shown.length} of ${rows.length} prices`} aside={
        <button className="text-sm px-3 py-1 rounded-md border border-rule hover:border-[var(--muted)]"
          onClick={async () => setMsg(await exportCSV(`value_${ref.season}_wk${ref.week}.csv`, shown.map(({ g, ...v }) => ({ game: label(g), kickoff_utc: g.kickoff_utc, ...v, game_confidence: g.confidence.label }))))}>{msg || EXPORT_LABEL}</button>}>
        <div className="flex flex-wrap gap-4 items-center mb-4 text-sm">
          <EdgeSlider />
          <Toggle on={onlyFlagged} set={setOnlyFlagged} label="Only show flagged" />
          <select value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Market"><option value="All">All markets</option><option value="moneyline">Moneyline</option><option value="spread">Spread</option><option value="total">Total</option></select>
          <select value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Team"><option value="All">All teams</option>{teams.map((t) => <option key={t}>{t}</option>)}</select>
        </div>
        {rows.length === 0 ? <Note>All games in this week have been played. Pick the current week to see open prices.</Note> :
          <SortTable rows={shown} cols={cols} initial="edge" rowKey={(r) => r.g.game_id + r.selection} empty={`Nothing clears a ${minEdge.toFixed(1)}-point edge. Lower the threshold or turn off "Only show flagged".`} />}
        <div className="grid md:grid-cols-2 gap-4 mt-4 text-[13px] text-muted">
          <div>
            <p className="font-semibold text-fg mb-1">How these are calculated</p>
            <p>Raw implied probability: +A → 100 / (A + 100); −A → A / (A + 100). No-vig: each side's raw probability divided by the sum of both. Expected profit per unit at decimal odds D: p × (D − 1) − (1 − p). ROI is that number as a percent of stake.</p>
          </div>
          <div>
            <p className="font-semibold text-fg mb-1">Read this before acting on an edge</p>
            <p>In walk-forward backtests the closing market was more accurate than this model, and flat-betting every flagged edge at closing prices lost money (see Track record). An edge usually means the model is missing something: injury news, lineup changes, a stale line. Prices: {meta.odds_source === "the-odds-api" ? "best available across books from The Odds API" : "nflverse consensus lines, which may lag live books"}.</p>
          </div>
        </div>
        {!meta.td_market_available && <p className="text-xs text-muted mt-3">Anytime-TD prices aren't connected, so player props aren't in this table. See Data & method for how to enable them.</p>}
      </Section>
    </div>
  );
}
