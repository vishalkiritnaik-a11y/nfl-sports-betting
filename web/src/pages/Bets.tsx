import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../App";
import { Note, Section, SortTable, type Col } from "../components/ui";
import { loadWeek } from "../lib/data";
import { grade, loadBets, newBet, optionsFor, parseAdd, profit, saveBets, type Alt, type Bet, type Outcome } from "../lib/bets";
import { label as gameLabel } from "../lib/derive";
import { pct, units } from "../lib/format";
import { fmtAmerican } from "../lib/odds";
import type { WeekData } from "../types";

const fileFor = (season: number, week: number) => `weeks/${season}_${String(week).padStart(2, "0")}.json`;
const OUT_COLOR: Record<Outcome, string> = { won: "var(--pos)", lost: "var(--neg)", push: "var(--muted)", void: "var(--muted)", pending: "var(--muted)" };
const OUT_TEXT: Record<Outcome, string> = { won: "Won", lost: "Lost", push: "Push", void: "Void (didn't play)", pending: "Pending" };

function useWeeks(keys: string[]) {
  const [weeks, set] = useState<Record<string, WeekData>>({});
  const sig = [...new Set(keys)].sort().join(",");
  useEffect(() => {
    let alive = true;
    Promise.all(sig.split(",").filter(Boolean).map((f) => loadWeek(f).then((w) => [f, w] as const).catch(() => null)))
      .then((rs) => alive && set(Object.fromEntries(rs.filter(Boolean) as [string, WeekData][])));
    return () => { alive = false; };
  }, [sig]);
  return weeks;
}

function AddForm({ onAdd }: { onAdd: (b: Bet) => void }) {
  const { week } = useApp();
  const games = week!.games;
  const [gid, setGid] = useState(games.find((g) => !g.result)?.game_id ?? games[0]?.game_id);
  const g = games.find((x) => x.game_id === gid);
  const opts = useMemo(() => (g ? optionsFor(g, week!.td) : []), [g, week]);
  const [oi, setOi] = useState(0);
  const opt: Alt | undefined = opts[oi];
  const [line, setLine] = useState<string>("");
  const [odds, setOdds] = useState<string>("");
  const [stake, setStake] = useState<string>("1");
  useEffect(() => { setOi(0); }, [gid]);
  useEffect(() => { setLine(opt?.line != null ? String(opt.line) : ""); setOdds(opt?.odds != null ? String(Math.round(opt.odds)) : ""); }, [opt]);
  const o = Number(odds);
  const oddsOk = odds !== "" && (o >= 100 || o <= -100);
  const needsLine = opt?.market === "spread" || opt?.market === "total";
  const ok = !!g && !!opt && oddsOk && Number(stake) > 0 && (!needsLine || line !== "");
  return (
    <form className="grid gap-3" onSubmit={(e) => {
      e.preventDefault();
      if (!ok || !g || !opt) return;
      onAdd(newBet(g, week!, opt, o, Number(stake), needsLine ? Number(line) : null));
    }}>
      <div className="flex flex-wrap gap-3 items-end text-sm">
        <label className="grid gap-1"><span className="text-muted text-xs">Game</span>
          <select id="bet-game" value={gid} onChange={(e) => setGid(e.target.value)}>
            {games.map((x) => <option key={x.game_id} value={x.game_id}>{gameLabel(x)}{x.result ? " (final)" : ""}</option>)}
          </select></label>
        <label className="grid gap-1"><span className="text-muted text-xs">Bet</span>
          <select id="bet-option" value={oi} onChange={(e) => setOi(Number(e.target.value))} className="max-w-[260px]">
            {opts.map((x, i) => <option key={x.label} value={i}>{x.label} (model {pct(x.model_p)})</option>)}
          </select></label>
        {needsLine && <label className="grid gap-1"><span className="text-muted text-xs">Line you got</span>
          <input id="bet-line" type="text" inputMode="decimal" value={line} onChange={(e) => setLine(e.target.value)} className="w-20" /></label>}
        <label className="grid gap-1"><span className="text-muted text-xs">Odds you got</span>
          <input id="bet-odds" type="text" inputMode="numeric" value={odds} onChange={(e) => setOdds(e.target.value)} className="w-20" placeholder="-110" /></label>
        <label className="grid gap-1"><span className="text-muted text-xs">Stake (units)</span>
          <input id="bet-stake" type="text" inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} className="w-16" /></label>
        <button type="submit" disabled={!ok} className="px-4 py-1.5 rounded-md font-semibold disabled:opacity-40" style={{ background: "var(--model)", color: "var(--ink)" }}>Add bet</button>
      </div>
      {!oddsOk && odds !== "" && <p className="text-xs" style={{ color: "var(--warn)" }}>Odds must be American format, like -110 or +150.</p>}
      {opt && opt.odds == null && <p className="text-xs text-muted">No book price in the data for this one. Enter the odds you got.</p>}
    </form>
  );
}

export default function BetsPage() {
  const [sp, setSp] = useSearchParams();
  const [bets, setBets] = useState<Bet[]>(loadBets);
  const [msg, setMsg] = useState("");
  const [showIO, setShowIO] = useState(false);
  const [io, setIo] = useState("");
  const update = (b: Bet[]) => { setBets(b); if (!saveBets(b)) setMsg("This browser is blocking storage, so bets won't be kept after you close the page."); };

  // one-tap add from a link: #/bets?add=GAME:market:side:line:odds
  const add = sp.get("add");
  const handled = useRef<string | null>(null);
  useEffect(() => {
    if (!add || handled.current === add) return;
    handled.current = add;
    const p = parseAdd(add);
    sp.delete("add"); setSp(sp, { replace: true });
    if (!p) { setMsg("That link isn't a valid bet."); return; }
    const [season, wk] = p.game_id.split("_").map(Number);
    loadWeek(fileFor(season, wk)).then((w) => {
      const g = w.games.find((x) => x.game_id === p.game_id);
      if (!g) { setMsg("Couldn't find that game in the data."); return; }
      const opt = optionsFor(g, w.td).find((o) => o.market === p.market && o.side === p.side);
      if (!opt) { setMsg("Couldn't find that bet option for the game."); return; }
      const line = p.line ?? opt.line;
      const odds = p.odds ?? opt.odds;
      if (odds == null) { setMsg("The link needs odds for this bet."); return; }
      const cur = loadBets();
      if (cur.some((b) => b.game_id === g.game_id && b.market === p.market && b.side === p.side && b.line === line)) { setMsg("That bet is already on your list."); return; }
      const b = newBet(g, w, opt, odds, 1, line);
      update([b, ...cur]);
      setMsg(`Added ${b.label} (${b.matchup}).`);
    }).catch(() => setMsg("Couldn't load that week's data."));
  }, [add]); // eslint-disable-line react-hooks/exhaustive-deps

  const weeks = useWeeks(bets.map((b) => fileFor(b.season, b.week)));
  const rows = bets.map((b) => {
    const w = weeks[fileFor(b.season, b.week)];
    const g = w?.games.find((x) => x.game_id === b.game_id);
    const out = w ? grade(b.market, b.side, b.line, g, w.td) : "pending";
    const gameAlts = b.alts.filter((a) => a.market !== "anytime_td");
    const likely = [...gameAlts].sort((x, y) => y.model_p - x.model_p)[0];
    const value = [...b.alts].filter((a) => a.ev != null).sort((x, y) => (y.ev ?? -9) - (x.ev ?? -9))[0];
    const gr = (a?: Alt) => (a && w ? grade(a.market, a.side, a.line, g, w.td) : "pending");
    return { b, g, out, pl: profit(out, b.odds, b.stake), likely, likelyOut: gr(likely), value, valueOut: gr(value) };
  });
  const settled = rows.filter((r) => r.out !== "pending");
  const sum = (f: (r: typeof rows[number]) => number) => settled.reduce((a, r) => a + f(r), 0);
  const staked = sum((r) => (r.out === "won" || r.out === "lost" ? r.b.stake : 0));
  const likelyPL = sum((r) => (r.likely?.odds != null ? profit(r.likelyOut, r.likely.odds, r.b.stake) : 0));
  const count = (o: Outcome) => settled.filter((r) => r.out === o).length;

  const cols: Col<typeof rows[number]>[] = [
    { key: "game", label: "Game", sort: (r) => r.b.kickoff_utc, render: (r) => (
      <Link className="hover:underline" to={{ pathname: `/game/${r.b.game_id}`, search: `?w=${r.b.season}_${String(r.b.week).padStart(2, "0")}` }}>
        {r.b.matchup}<div className="text-xs text-muted">{r.b.season} wk {r.b.week}</div></Link>) },
    { key: "bet", label: "Your bet", sort: (r) => r.b.label, render: (r) => <span className="font-medium">{r.b.label}</span> },
    { key: "odds", label: "Odds", align: "right", sort: (r) => r.b.odds, render: (r) => fmtAmerican(r.b.odds) },
    { key: "p", label: "Model chance", align: "right", sort: (r) => r.b.model_p, render: (r) => pct(r.b.model_p, 1) },
    { key: "out", label: "Result", sort: (r) => r.out, render: (r) => <span style={{ color: OUT_COLOR[r.out] }}>{OUT_TEXT[r.out]}{r.g?.result ? <span className="text-xs text-muted"> {r.g.result.away_score}–{r.g.result.home_score}</span> : null}</span> },
    { key: "pl", label: "Profit", align: "right", sort: (r) => r.pl, render: (r) => r.out === "pending" ? <span className="text-muted">—</span> : <span style={{ color: r.pl > 0 ? "var(--pos)" : r.pl < 0 ? "var(--neg)" : undefined }}>{units(r.pl)}</span> },
    { key: "alt", label: "More likely option", render: (r) => !r.likely ? "—" : r.likely.label === r.b.label ? <span className="text-muted">Yours was the most likely</span> : (
      <span>{r.likely.label} <span className="text-muted">({pct(r.likely.model_p)}{r.likely.odds != null ? `, ${fmtAmerican(r.likely.odds)}` : ""})</span>
        {r.likelyOut !== "pending" && <span style={{ color: OUT_COLOR[r.likelyOut] }}> {OUT_TEXT[r.likelyOut].toLowerCase()}</span>}</span>) },
    { key: "x", label: <span className="sr-only">Remove</span>, render: (r) => <button className="text-xs text-muted hover:text-fg" aria-label={`Remove ${r.b.label}`}
      onClick={(e) => { e.stopPropagation(); update(bets.filter((x) => x.id !== r.b.id)); }}>Remove</button> },
  ];

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">My bets</h1>
        <p className="text-muted text-sm max-w-[80ch]">Log the bets you place. Each one is graded when the game goes final and compared with the alternatives in that game, using the model's numbers from when you logged it. Your list is saved in this browser only. It isn't uploaded anywhere and won't appear on other devices.</p>
      </div>
      {msg && <div className="panel p-3 text-sm" role="status">{msg} <button className="text-muted ml-2" onClick={() => setMsg("")}>Dismiss</button></div>}

      <Section title="Add a bet" aside={<span className="text-xs text-muted">From the week selected above. Switch weeks to log other games.</span>}>
        <AddForm onAdd={(b) => { update([b, ...bets]); setMsg(`Added ${b.label} (${b.matchup}).`); }} />
      </Section>

      {settled.length > 0 && (
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-px rounded-[10px] overflow-hidden border border-rule bg-[var(--rule)]">
          {[["Record", `${count("won")}-${count("lost")}${count("push") ? `-${count("push")}` : ""}`, `${settled.length} settled, ${rows.length - settled.length} pending`],
            ["Profit", units(sum((r) => r.pl)), staked ? `ROI ${((sum((r) => r.pl) / staked) * 100).toFixed(1)}% on ${staked} units` : ""],
            ["Model's average chance", pct(settled.reduce((a, r) => a + (r.b.model_p ?? 0), 0) / settled.length), `you won ${pct(count("won") / Math.max(1, count("won") + count("lost")))} of decided bets`],
            ["If you'd taken the most likely option", units(likelyPL), "same stakes, consensus prices"],
          ].map(([k, v, s]) => (
            <div key={k} className="bg-panel p-4"><dt className="text-xs text-muted">{k}</dt><dd className="display text-[24px] tnum mt-1">{v}</dd><dd className="text-xs text-muted">{s}</dd></div>))}
        </dl>)}

      <Section title={`Your bets (${bets.length})`} aside={<button className="text-sm link" onClick={() => { setShowIO(!showIO); setIo(JSON.stringify(bets)); }} aria-expanded={showIO}>Back up or move bets</button>}>
        {showIO && (
          <div className="grid gap-2 mb-4">
            <Note>Copy this text to keep a backup or move your list to another device. To restore, paste a backup here and choose Replace list.</Note>
            <textarea id="bets-io" className="w-full h-28 text-xs p-2 rounded-md" style={{ background: "var(--raised)", border: "1px solid var(--rule)", color: "var(--fg)" }} value={io} onChange={(e) => setIo(e.target.value)} />
            <div className="flex gap-3">
              <button className="text-sm px-3 py-1 rounded-md border border-rule" onClick={async () => { try { await navigator.clipboard.writeText(io); setMsg("Copied your bets."); } catch { setMsg("Copy was blocked. Select the text and copy it manually."); } }}>Copy</button>
              <button className="text-sm px-3 py-1 rounded-md border border-rule" onClick={() => { try { const b = JSON.parse(io); if (!Array.isArray(b)) throw 0; update(b); setMsg(`Restored ${b.length} bets.`); } catch { setMsg("That text isn't a valid backup."); } }}>Replace list</button>
            </div>
          </div>)}
        {bets.length === 0 ? <Note>No bets yet. Add one above, or open a share link from Claude to add it in one tap.</Note> : (
          <SortTable rows={rows} cols={cols} initial="game" rowKey={(r) => r.b.id} expand={(r) => (
            <div className="grid md:grid-cols-[1fr_1fr] gap-5 py-2 text-[13.5px]">
              <div>
                <p className="mb-2">{r.likely && r.likely.label !== r.b.label
                  ? <>The model's most likely outcome in this game was <b>{r.likely.label}</b> at {pct(r.likely.model_p)}, against {pct(r.b.model_p)} for your bet{r.likely.odds != null ? `, but at ${fmtAmerican(r.likely.odds)} it paid less` : ""}.</>
                  : <>Your bet was the model's most likely outcome in this game.</>}
                  {r.value && r.value.label !== r.b.label && r.value.ev != null && <> Best expected value by the model: <b>{r.value.label}</b> ({r.value.ev >= 0 ? "+" : ""}{(r.value.ev * 100).toFixed(0)}¢ per $1, {pct(r.value.model_p)} to hit){r.valueOut !== "pending" ? `, which ${r.valueOut === "won" ? "won" : r.valueOut === "lost" ? "lost" : "pushed"}` : ""}.</>}
                  {r.value && r.value.label === r.b.label && <> It was also the model's best expected value in the game.</>}
                </p>
                <p className="text-xs text-muted">Numbers are from when you logged the bet ({new Date(r.b.logged_at).toLocaleString()}){r.b.snapshot_backtest ? ", using the backtest projection because the game had already been played" : ""}. Most likely and best value are often different bets: favourites win more often but pay less.</p>
              </div>
              <div className="scroll-x"><table className="dtable text-[13px]"><thead><tr><th>Option</th><th style={{ textAlign: "right" }}>Price</th><th style={{ textAlign: "right" }}>Model</th><th style={{ textAlign: "right" }}>EV / $1</th><th>Result</th></tr></thead>
                <tbody>{r.b.alts.filter((a) => a.market !== "anytime_td").map((a) => { const w = weeks[fileFor(r.b.season, r.b.week)]; const o = w ? grade(a.market, a.side, a.line, r.g, w.td) : "pending";
                  return <tr key={a.label} style={{ fontWeight: a.label === r.b.label ? 600 : 400 }}><td>{a.label}{a.label === r.b.label ? " (yours)" : ""}</td><td className="text-right">{fmtAmerican(a.odds)}</td><td className="text-right">{pct(a.model_p, 1)}</td>
                    <td className="text-right" style={{ color: (a.ev ?? 0) > 0 ? "var(--pos)" : "var(--neg)" }}>{a.ev == null ? "—" : `${a.ev >= 0 ? "+" : ""}${(a.ev * 100).toFixed(0)}¢`}</td><td style={{ color: OUT_COLOR[o] }}>{o === "pending" ? "—" : OUT_TEXT[o]}</td></tr>; })}</tbody></table></div>
            </div>)} />)}
        <p className="text-xs text-muted mt-3">Click a bet to see every option in that game. Results update when the dashboard refreshes after the game.</p>
      </Section>
    </div>
  );
}

