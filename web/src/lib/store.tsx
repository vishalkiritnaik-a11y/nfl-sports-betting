import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// Per-viewer conveniences only (watchlist, threshold, display toggles). Browser storage can be
// unavailable (private windows, previews), so every access is guarded and the app works without it.
function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch { return fallback; }
}
function write(key: string, v: unknown) {
  try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* storage unavailable */ }
}

export type ProbView = "model" | "market";

interface Settings {
  minEdge: number; setMinEdge: (n: number) => void;
  probView: ProbView; setProbView: (v: ProbView) => void;
  withoutUncertain: boolean; setWithoutUncertain: (b: boolean) => void;
  watch: { games: string[]; players: string[] };
  toggleGame: (id: string) => void; togglePlayer: (id: string) => void;
}

const Ctx = createContext<Settings | null>(null);

export function SettingsProvider({ children, defaultEdge }: { children: ReactNode; defaultEdge: number }) {
  const [minEdge, setMinEdgeS] = useState<number>(() => read("ne.minEdge", defaultEdge));
  const [probView, setProbViewS] = useState<ProbView>(() => read("ne.probView", "model"));
  const [withoutUncertain, setWU] = useState<boolean>(() => read("ne.withoutUncertain", false));
  const [watch, setWatch] = useState(() => read("ne.watch", { games: [] as string[], players: [] as string[] }));
  useEffect(() => write("ne.minEdge", minEdge), [minEdge]);
  useEffect(() => write("ne.probView", probView), [probView]);
  useEffect(() => write("ne.withoutUncertain", withoutUncertain), [withoutUncertain]);
  useEffect(() => write("ne.watch", watch), [watch]);
  const toggle = (k: "games" | "players") => (id: string) =>
    setWatch((w) => ({ ...w, [k]: w[k].includes(id) ? w[k].filter((x) => x !== id) : [...w[k], id] }));
  const toggleGame = useCallback(toggle("games"), []);
  const togglePlayer = useCallback(toggle("players"), []);
  const v = useMemo(() => ({ minEdge, setMinEdge: setMinEdgeS, probView, setProbView: setProbViewS, withoutUncertain,
    setWithoutUncertain: setWU, watch, toggleGame, togglePlayer }), [minEdge, probView, withoutUncertain, watch, toggleGame, togglePlayer]);
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>;
}

export function useSettings() {
  const c = useContext(Ctx);
  if (!c) throw new Error("SettingsProvider missing");
  return c;
}
