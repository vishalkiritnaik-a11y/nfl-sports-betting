import { useMemo, useState, type ReactNode } from "react";
import type { Confidence, TeamInfo } from "../types";
import { useSettings } from "../lib/store";
import { visibleColor } from "../lib/format";

export function TeamMark({ team, info, size = 28 }: { team: string; info?: TeamInfo; size?: number }) {
  const [broken, setBroken] = useState(false);
  if (info?.logo && !broken)
    return <img src={info.logo} alt="" width={size} height={size} onError={() => setBroken(true)} style={{ width: size, height: size }} className="shrink-0 object-contain" loading="lazy" />;
  return (
    <span aria-hidden className="inline-grid place-items-center rounded-full shrink-0 text-[10px] font-bold"
      style={{ width: size, height: size, background: info?.color ?? "#334", color: "#fff" }}>{team}</span>
  );
}

/** Signature element: two-team probability bar with a brass market tick. */
export function SplitBar({ pAway, away, home, teams, marketHome, height = 10, showMarket = true, tickColor = "var(--market)", tickLabel = "Market (no-vig)" }: {
  pAway: number; away: string; home: string; teams: Record<string, TeamInfo>; marketHome?: number | null; height?: number; showMarket?: boolean;
  tickColor?: string; tickLabel?: string;
}) {
  const ca = visibleColor(teams[away]?.color, teams[away]?.color2);
  let ch = visibleColor(teams[home]?.color, teams[home]?.color2);
  if (ch === ca) ch = visibleColor(teams[home]?.color2, teams[home]?.color);
  const mAway = marketHome != null ? 1 - marketHome : null;
  return (
    <div className="relative w-full" style={{ height }} role="img"
      aria-label={`${away} ${(pAway * 100).toFixed(0)}%, ${home} ${((1 - pAway) * 100).toFixed(0)}%${mAway != null ? `; ${tickLabel} ${away} ${(mAway * 100).toFixed(0)}%` : ""}`}>
      <div className="absolute inset-0 flex overflow-hidden rounded-full" style={{ background: "var(--raised)" }}>
        <div className="h-full fill-in" style={{ width: `${pAway * 100}%`, background: ca, boxShadow: "inset -1px 0 0 rgba(0,0,0,.35)" }} />
        <div className="h-full fill-in-r" style={{ width: `${(1 - pAway) * 100}%`, background: ch }} />
      </div>
      <div className="absolute top-[-3px] bottom-[-3px] w-px" style={{ left: "50%", background: "rgba(230,236,245,.35)" }} />
      {showMarket && mAway != null && (
        <div className="absolute" style={{ left: `calc(${mAway * 100}% - 5px)`, top: -5, width: 10, height: height + 10 }} title={`${tickLabel}: ${away} ${(mAway * 100).toFixed(1)}%`}>
          <div className="mx-auto h-full w-[3px] rounded" style={{ background: tickColor, boxShadow: "0 0 0 1.5px var(--ink)" }} />
        </div>
      )}
    </div>
  );
}

export function ConfidenceTag({ c }: { c?: Confidence }) {
  if (!c || c.label === "n/a") return null;
  const color = c.label === "High" ? "var(--pos)" : c.label === "Medium" ? "var(--muted)" : "var(--warn)";
  return (
    <span className="inline-flex items-center gap-1 text-xs" style={{ color }} title={c.reasons.join("\n")}>
      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} /> {c.label} confidence
    </span>
  );
}

export function StatusTag({ s }: { s: string }) {
  if (!s || s === "Active" || s === "Played") return null;
  const col = s === "Out" ? "var(--neg)" : s === "Doubtful" ? "var(--neg)" : s === "Questionable" ? "var(--warn)" : "var(--muted)";
  return <span className="text-[11px] px-1.5 py-0.5 rounded" style={{ color: col, border: `1px solid ${col}` }}>{s}</span>;
}

export function Edge({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-muted">—</span>;
  return <span className="tnum" style={{ color: v > 0 ? "var(--pos)" : v < 0 ? "var(--neg)" : undefined }}>{v > 0 ? "+" : ""}{v.toFixed(1)}</span>;
}

export function Section({ title, aside, children, className = "" }: { title: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel p-4 ${className}`}>
      <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
        <h2 className="text-[17px] font-semibold wide">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-[13px] text-muted leading-relaxed max-w-[75ch]">{children}</p>;
}

export function Loading() { return <div className="p-8 text-muted">Loading data…</div>; }
export function ErrorBox({ msg }: { msg: string }) {
  return <div className="panel p-6 m-4"><p className="font-semibold">Data didn't load.</p><p className="text-muted text-sm mt-1">{msg}</p></div>;
}

export function Star({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button onClick={(e) => { e.preventDefault(); e.stopPropagation(); onClick(); }} aria-pressed={on} aria-label={on ? `Remove ${label} from watchlist` : `Add ${label} to watchlist`}
      title={on ? "On your watchlist" : "Add to watchlist"} className="text-lg leading-none px-1" style={{ color: on ? "var(--market)" : "var(--muted)" }}>
      {on ? "★" : "☆"}
    </button>
  );
}

export interface Col<T> {
  key: string; label: ReactNode; render: (r: T) => ReactNode; sort?: (r: T) => number | string | null | undefined;
  align?: "right" | "left"; title?: string; className?: string;
}

export function SortTable<T>({ rows, cols, initial, desc = true, rowKey, onRow, empty = "Nothing matches these filters.", expand }: {
  rows: T[]; cols: Col<T>[]; initial?: string; desc?: boolean; rowKey: (r: T) => string; onRow?: (r: T) => void; empty?: string;
  expand?: (r: T) => ReactNode | null;
}) {
  const [key, setKey] = useState(initial ?? cols[0].key);
  const [d, setD] = useState(desc);
  const [open, setOpen] = useState<string | null>(null);
  const sorted = useMemo(() => {
    const c = cols.find((x) => x.key === key);
    if (!c?.sort) return rows;
    const s = [...rows].sort((a, b) => {
      const va = c.sort!(a), vb = c.sort!(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * (d ? -1 : 1);
    });
    return s;
  }, [rows, cols, key, d]);
  return (
    <div className="scroll-x">
      <table className="dtable text-[14px]">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} style={{ textAlign: c.align ?? "left" }} title={c.title} aria-sort={key === c.key ? (d ? "descending" : "ascending") : "none"}>
                {c.sort ? (
                  <button onClick={() => (key === c.key ? setD(!d) : (setKey(c.key), setD(true)))}>
                    {c.label}{key === c.key ? (d ? " ↓" : " ↑") : ""}
                  </button>
                ) : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && <tr><td colSpan={cols.length} className="text-muted py-6">{empty}</td></tr>}
          {sorted.map((r) => {
            const k = rowKey(r);
            const ex = expand && open === k ? expand(r) : null;
            return [
              <tr key={k} className={onRow || expand ? "cursor-pointer" : ""} onClick={() => (expand ? setOpen(open === k ? null : k) : onRow?.(r))}
                tabIndex={onRow || expand ? 0 : undefined} onKeyDown={(e) => { if (e.key === "Enter") (expand ? setOpen(open === k ? null : k) : onRow?.(r)); }}
                aria-expanded={expand ? open === k : undefined}>
                {cols.map((c) => <td key={c.key} style={{ textAlign: c.align ?? "left" }} className={c.className}>{c.render(r)}</td>)}
              </tr>,
              ex ? <tr key={k + "-x"}><td colSpan={cols.length} className="bg-[var(--raised)]">{ex}</td></tr> : null,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Toggle({ on, set, label }: { on: boolean; set: (b: boolean) => void; label: string }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm cursor-pointer select-none">
      <button role="switch" aria-checked={on} onClick={() => set(!on)} className="relative w-9 h-5 rounded-full transition-colors"
        style={{ background: on ? "var(--model)" : "var(--rule)" }}>
        <span className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all" style={{ left: on ? 18 : 2 }} />
      </button>
      {label}
    </label>
  );
}

export function EdgeSlider() {
  const { minEdge, setMinEdge } = useSettings();
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-muted">Min edge</span>
      <input type="range" min={0} max={15} step={0.5} value={minEdge} onChange={(e) => setMinEdge(parseFloat(e.target.value))} aria-label="Minimum edge in percentage points" />
      <span className="tnum w-14">{minEdge.toFixed(1)} pts</span>
    </label>
  );
}

export function ProbViewToggle() {
  const { probView, setProbView } = useSettings();
  return (
    <div className="inline-flex rounded-md overflow-hidden border border-rule text-sm" role="group" aria-label="Probability shown">
      {(["model", "market"] as const).map((v) => (
        <button key={v} onClick={() => setProbView(v)} aria-pressed={probView === v}
          className="px-3 py-1" style={{ background: probView === v ? (v === "model" ? "var(--model)" : "var(--market)") : "transparent", color: probView === v ? "var(--ink)" : "var(--fg)" }}>
          {v === "model" ? "Model" : "Market"}
        </button>
      ))}
    </div>
  );
}

/** Anytime-TD score out of 10: ten segments coloured by tier. */
export function ScoreBadge({ c }: { c?: Confidence }) {
  if (!c || c.score == null) return <span className="text-muted">—</span>;
  const col = c.label === "High" ? "var(--pos)" : c.label === "Medium" ? "var(--model)" : "var(--muted)";
  const dropped = c.base_score != null && c.base_score > c.score;
  return (
    <span className="inline-flex items-center gap-2" title={c.reasons.join("\n")} aria-label={`Score ${c.score} out of 10, ${c.label}`}>
      <span className="inline-flex gap-[2px]" aria-hidden>
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className="inline-block w-[5px] h-3 rounded-[1px]" style={{ background: i < c.score! ? col : "var(--rule)" }} />
        ))}
      </span>
      <span className="tnum font-semibold" style={{ color: col }}>{c.score}</span>
      {dropped && <span className="text-[11px] text-muted">was {c.base_score}</span>}
      {c.reasons.some((r) => r.startsWith("Role check")) && <span className="text-[11px]" style={{ color: "var(--warn)" }}>role check</span>}
    </span>
  );
}
