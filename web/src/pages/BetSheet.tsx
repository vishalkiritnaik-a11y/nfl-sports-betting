import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useApp } from "../App";
import { Note, TeamMark, Toggle } from "../components/ui";
import { usePicks } from "../lib/data";
import { kickoffLocal, pct, units } from "../lib/format";
import { fmtAmerican } from "../lib/odds";
import type { Game, Rec, RecPick } from "../types";

const MKT = [["spread", "Spread"], ["moneyline", "Moneyline"], ["total", "Total"]] as const;
const VERDICT_STYLE: Record<string, { bg: string; fg: string }> = {
  Bet: { bg: "var(--pos)", fg: "#06231c" },
  Lean: { bg: "color-mix(in srgb, var(--market) 30%, transparent)", fg: "var(--market)" },
  Pass: { bg: "transparent", fg: "var(--muted)" },
};
const RES = { won: ["Won", "var(--pos)"], lost: ["Lost", "var(--neg)"], push: ["Push", "var(--muted)"], pending: ["Pending", "var(--muted)"] } as const;

function Verdict({ v }: { v: string }) {
  const s = VERDICT_STYLE[v];
  return <span className="text-xs font-semibold px-2 py-0.5 rounded border" style={{ background: s.bg, color: s.fg, borderColor: v === "Pass" ? "var(--rule)" : s.bg }}>{v}</span>;
}

function Score({ n }: { n: number }) {
  const c = n >= 7 ? "var(--pos)" : n === 6 ? "var(--market)" : "var(--muted)";
  return (
    <span className="inline-flex items-center gap-2" aria-label={`Score ${n} out of 10`}>
      <span className="tnum font-semibold text-lg" style={{ color: c }}>{n}</span>
      <span className="hidden sm:flex gap-[2px]" aria-hidden>
        {Array.from({ length: 10 }, (_, i) => <span key={i} className="w-[5px] h-3 rounded-sm" style={{ background: i < n ? c : "var(--rule)" }} />)}
      </span>
    </span>
  );
}

function Row({ name, r, graded, done }: { name: string; r?: Rec; graded?: RecPick; done: boolean }) {
  const [open, setOpen] = useState(false);
  if (!r && !graded) return (
    <div className="grid grid-cols-[88px_1fr] gap-3 py-3 border-t border-rule text-sm"><span className="text-muted">{name}</span><span className="text-muted">{done ? "No pick logged before kickoff (this view started Oct 12, 2026)" : "No line posted yet"}</span></div>
  );
  const label = r?.label ?? graded!.label, odds = r?.odds ?? graded!.odds, score = r?.score ?? graded!.score;
  const verdict = r?.verdict ?? graded!.verdict, pWin = r?.p_win ?? graded!.p_win;
  return (
    <div className="border-t border-rule">
      <button className="w-full grid grid-cols-[88px_1fr_auto] sm:grid-cols-[88px_1fr_120px_70px_60px] gap-3 items-center py-3 text-left hover:bg-white/[.02]"
        onClick={() => r && setOpen(!open)} aria-expanded={open} disabled={!r}>
        <span className="text-muted text-sm">{name}</span>
        <span className="min-w-0">
          <span className="font-semibold">{label}</span> <span className="tnum text-muted">{fmtAmerican(odds)}</span>
          <span className="block text-xs text-muted sm:hidden">{pct(pWin)} to win{graded && graded.result !== "pending" ? ` · ${RES[graded.result][0]}` : ""}</span>
        </span>
        <span className="hidden sm:block"><Score n={score} /></span>
        <span className="sm:hidden tnum font-semibold">{score}/10</span>
        <span className="hidden sm:block"><Verdict v={verdict} /></span>
        <span className="hidden sm:block text-right text-sm">
          {graded && graded.result !== "pending" ? <span style={{ color: RES[graded.result][1] }}>{RES[graded.result][0]}</span> : <span className="tnum text-muted">{pct(pWin)}</span>}
        </span>
      </button>
      <div className="sm:hidden -mt-2 pb-2 pl-[100px]"><Verdict v={verdict} /></div>
      {open && r && (
        <ul className="pb-3 pl-[100px] grid gap-1.5 text-sm">
          {r.why.map((w) => (
            <li key={w.factor} className="grid grid-cols-[46px_1fr] gap-2">
              <span className="tnum text-right" style={{ color: w.points > 0 ? "var(--pos)" : w.points < 0 ? "var(--neg)" : "var(--muted)" }}>
                {w.points > 0 ? "+" : ""}{Number(w.points.toFixed(1))}
              </span>
              <span><span className="text-muted">{w.factor}:</span> {w.text}</span>
            </li>
          ))}
          <li className="text-xs text-muted pt-1">Starts at 5. Other side scores {r.other_score}/10. Win chance shown is market-anchored ({pct(r.p_win)}); the stats model alone says {pct(r.p_model)}.</li>
        </ul>
      )}
    </div>
  );
}

function GameCard({ g, graded }: { g: Game; graded: RecPick[] }) {
  const { meta } = useApp();
  const { search } = useLocation();
  const [news, setNews] = useState(false);
  const k = kickoffLocal(g.kickoff_utc);
  const items = g.recs?.notes?.items ?? [];
  const final = g.result ? `${g.away.team} ${g.result.away_score}, ${g.home.team} ${g.result.home_score}` : null;
  return (
    <article className="panel p-4 min-w-0">
      <header className="flex items-center gap-3 mb-1 flex-wrap">
        <TeamMark team={g.away.team} info={meta.teams[g.away.team]} size={26} />
        <Link to={{ pathname: `/game/${g.game_id}`, search }} className="display text-lg hover:underline">{g.away.team} @ {g.home.team}</Link>
        <TeamMark team={g.home.team} info={meta.teams[g.home.team]} size={26} />
        <span className="text-sm text-muted ml-auto">{final ? `Final: ${final}` : `${k.day} · ${k.time}`}</span>
      </header>
      <div className="hidden sm:grid grid-cols-[88px_1fr_120px_70px_60px] gap-3 text-[11px] uppercase tracking-wide text-muted pt-2 pb-1">
        <span>Market</span><span>Pick</span><span>Score /10</span><span>Call</span><span className="text-right">{g.result ? "Result" : "Win chance"}</span>
      </div>
      {MKT.map(([m, name]) => <Row key={m} name={name} r={g.recs?.markets[m]} graded={graded.find((x) => x.market === m)} done={!!g.result} />)}
      {items.length > 0 && (
        <div className="border-t border-rule pt-2">
          <button className="text-sm text-muted hover:text-fg" onClick={() => setNews(!news)} aria-expanded={news}>{news ? "▾" : "▸"} News & sources ({items.length})</button>
          {news && (
            <ul className="mt-2 grid gap-1.5 text-sm">
              {items.map((n, i) => <li key={i}>{n.text} {n.url ? <a className="link text-muted" href={n.url} target="_blank" rel="noreferrer">({n.source})</a> : <span className="text-muted">({n.source})</span>}</li>)}
              {g.recs?.opening?.source && <li className="text-xs text-muted">Opening line: {g.recs.opening.source}</li>}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

export default function BetSheet() {
  const { week, ref } = useApp();
  const picks = usePicks();
  const [onlyAction, setOnlyAction] = useState(false);
  const ledger = picks.data?.recs ?? [];
  const hasPick = (g: Game) => !!g.recs || ledger.some((x) => x.game_id === g.game_id);
  const all = [...week!.games].sort((a, b) => Number(!!a.result) - Number(!!b.result) || a.kickoff_utc.localeCompare(b.kickoff_utc));
  const games = all.filter((g) => !g.result || hasPick(g));
  const unlogged = all.length - games.length;
  const shown = games.filter((g) => {
    if (!onlyAction) return true;
    const rs = g.recs ? Object.values(g.recs.markets) : ledger.filter((x) => x.game_id === g.game_id);
    return rs.some((r) => r && r.verdict !== "Pass");
  });
  const settled = ledger.filter((r) => r.verdict !== "Pass" && (r.result === "won" || r.result === "lost"));
  const byV = (v: string) => { const s = settled.filter((r) => r.verdict === v); return { w: s.filter((r) => r.result === "won").length, l: s.filter((r) => r.result === "lost").length, u: s.reduce((a, r) => a + r.profit, 0) }; };
  const bet = byV("Bet"), lean = byV("Lean");
  const anyRecs = games.some((g) => g.recs) || ledger.some((r) => games.some((g) => g.game_id === r.game_id));

  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">What to bet: {ref.season} {ref.label}</h1>
        <p className="text-muted text-sm max-w-[80ch]">
          One Spread, Moneyline and Total pick per game, each scored out of 10. Every pick starts at 5. Points are added or taken away for
          the stats model, line movement (where professional money went), price, published picks from betting sites, and injury news.
          The stats model alone can't go past 6, because it hasn't beaten closing lines on its own. <b>7+ = Bet</b>, <b>6 = Lean</b>,
          5 or lower = Pass. Tap a pick to see why.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <Toggle on={onlyAction} set={setOnlyAction} label="Only games with a Bet or Lean" />
        <span className="text-muted">
          Track record (graded before kickoff): Bets {bet.w}-{bet.l} ({units(bet.u)}) · Leans {lean.w}-{lean.l} ({units(lean.u)})
          {settled.length === 0 && " · starts this week"}
        </span>
      </div>
      {unlogged > 0 && <p className="text-sm text-muted">{unlogged} finished game{unlogged > 1 ? "s" : ""} this week kicked off before this view existed (Oct 12, 2026), so {unlogged > 1 ? "they have" : "it has"} no logged pick. See the Slate and Pick history tabs for those.</p>}
      {!anyRecs && <Note>Picks appear for upcoming games once sportsbook lines are posted. Finished games show the pick that was logged before kickoff.</Note>}
      <div className="grid gap-4 lg:grid-cols-2">
        {shown.map((g) => <GameCard key={g.game_id} g={g} graded={ledger.filter((x) => x.game_id === g.game_id)} />)}
      </div>
      <p className="text-xs text-muted max-w-[80ch]">
        Scores rank how strongly the evidence lines up. They are not guarantees. A Spread or Total pick at 6/10 still wins only about half the time.
        Sportsbook prices include a margin of 4–5%, so a Pass is the right call most of the time. Bet only what you can afford to lose.
      </p>
    </div>
  );
}
