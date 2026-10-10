import { createContext, useContext, useMemo, type ReactNode } from "react";
import { HashRouter, NavLink, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { useMeta, useWeek } from "./lib/data";
import { SettingsProvider } from "./lib/store";
import { ago } from "./lib/format";
import type { Meta, WeekData, WeekRef } from "./types";
import { ErrorBox, Loading } from "./components/ui";
import Slate from "./pages/Slate";
import GamePage from "./pages/Game";
import Touchdowns from "./pages/Touchdowns";
import Value from "./pages/Value";
import PerformancePage from "./pages/Performance";
import Compare from "./pages/Compare";
import Watchlist from "./pages/Watchlist";
import DataPage from "./pages/Data";

interface Ctx { meta: Meta; ref: WeekRef; week: WeekData | null; weekError: string | null; weekLoading: boolean }
const AppCtx = createContext<Ctx | null>(null);
export const useApp = () => {
  const c = useContext(AppCtx);
  if (!c) throw new Error("no app ctx");
  return c;
};

function WeekProvider({ meta, children }: { meta: Meta; children: ReactNode }) {
  const [sp] = useSearchParams();
  const w = sp.get("w");
  const ref = useMemo(() => {
    const byKey = (k: string) => meta.weeks.find((x) => `${x.season}_${String(x.week).padStart(2, "0")}` === k);
    return (w && byKey(w)) || meta.weeks.find((x) => x.kind === "current") || meta.weeks[0];
  }, [w, meta]);
  const wk = useWeek(ref?.file ?? null);
  return <AppCtx.Provider value={{ meta, ref, week: wk.data, weekError: wk.error, weekLoading: wk.loading }}>{children}</AppCtx.Provider>;
}

export function weekKey(r: WeekRef) { return `${r.season}_${String(r.week).padStart(2, "0")}`; }

function WeekSelect() {
  const { meta, ref } = useApp();
  const [sp, setSp] = useSearchParams();
  const seasons = [...new Set(meta.weeks.map((w) => w.season))].sort((a, b) => b - a);
  return (
    <div className="flex items-center gap-2">
      <label className="sr-only" htmlFor="season">Season</label>
      <select id="season" value={ref.season} onChange={(e) => {
        const s = parseInt(e.target.value, 10);
        const first = meta.weeks.filter((w) => w.season === s).sort((a, b) => (s === meta.season ? 0 : a.week - b.week))[0];
        const cur = meta.weeks.find((w) => w.season === s && w.kind === "current") ?? first;
        sp.set("w", weekKey(cur)); setSp(sp);
      }}>
        {seasons.map((s) => <option key={s} value={s}>{s} season</option>)}
      </select>
      <label className="sr-only" htmlFor="week">Week</label>
      <select id="week" value={weekKey(ref)} onChange={(e) => { sp.set("w", e.target.value); setSp(sp); }}>
        {meta.weeks.filter((w) => w.season === ref.season).sort((a, b) => a.week - b.week).map((w) => (
          <option key={weekKey(w)} value={weekKey(w)}>
            {w.label}{w.kind === "current" ? " (this week)" : w.kind === "lookahead" ? " (early look)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

const NAV = [
  ["/", "Slate"], ["/touchdowns", "Touchdowns"], ["/value", "Value"], ["/performance", "Track record"],
  ["/compare", "Compare"], ["/watchlist", "Watchlist"], ["/data", "Data & method"],
] as const;

function Shell({ children }: { children: ReactNode }) {
  const { meta } = useApp();
  const loc = useLocation();
  const search = loc.search;
  const gamesFresh = meta.sources.find((s) => s.file === "games.csv")?.source_updated;
  return (
    <div className="min-h-screen">
      <header className="border-b border-rule sticky z-20" style={{ top: "env(safe-area-inset-top, 0px)", background: "color-mix(in srgb, var(--ink) 92%, transparent)", backdropFilter: "blur(8px)" }}>
        <div className="max-w-[1400px] mx-auto px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <NavLink to={{ pathname: "/", search }} className="flex items-baseline gap-2">
            <span className="display text-[20px]">NFL Edge Board</span>
          </NavLink>
          <WeekSelect />
          <div className="ml-auto text-xs text-muted text-right leading-tight">
            Built {ago(meta.generated)}, stats and lines updated {ago(gamesFresh)}
            <br />An analysis tool, not betting advice
          </div>
        </div>
        <nav className="max-w-[1400px] mx-auto px-2 flex overflow-x-auto" aria-label="Sections">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={{ pathname: to, search }} end={to === "/"}
              className={({ isActive }) => `px-3 py-2 text-sm whitespace-nowrap border-b-2 ${isActive ? "border-[var(--model)] text-fg" : "border-transparent text-muted hover:text-fg"}`}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="max-w-[1400px] mx-auto px-4 py-5">{children}</main>
      <footer className="max-w-[1400px] mx-auto px-4 pb-10 pt-4 text-xs text-muted leading-relaxed">
        Probabilities are estimates with real uncertainty; a 70% favourite loses about three times in ten. Nothing here is a
        recommendation to bet. If gambling stops being fun, call or text 1-800-GAMBLER. Data: nflverse (CC-BY 4.0), FTN charting
        via nflverse, Open-Meteo. Model {meta.model_version}.
      </footer>
    </div>
  );
}

function Routed() {
  const { weekError, weekLoading, week } = useApp();
  const needsWeek = (el: ReactNode) => (weekError ? <ErrorBox msg={weekError} /> : weekLoading || !week ? <Loading /> : el);
  return (
    <Shell>
      <Routes>
        <Route path="/" element={needsWeek(<Slate />)} />
        <Route path="/game/:id" element={needsWeek(<GamePage />)} />
        <Route path="/touchdowns" element={needsWeek(<Touchdowns />)} />
        <Route path="/value" element={needsWeek(<Value />)} />
        <Route path="/performance" element={<PerformancePage />} />
        <Route path="/compare" element={needsWeek(<Compare />)} />
        <Route path="/watchlist" element={needsWeek(<Watchlist />)} />
        <Route path="/data" element={<DataPage />} />
        <Route path="*" element={<div className="text-muted">That page doesn't exist. Use the tabs above.</div>} />
      </Routes>
    </Shell>
  );
}

export default function App() {
  const meta = useMeta();
  if (meta.error) return <ErrorBox msg={meta.error} />;
  if (!meta.data) return <Loading />;
  return (
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <SettingsProvider defaultEdge={meta.data.default_min_edge_pp}>
        <WeekProvider meta={meta.data}>
          <Routed />
        </WeekProvider>
      </SettingsProvider>
    </HashRouter>
  );
}
