import { useEffect, useState } from "react";
import type { Meta, Performance, WeekData } from "../types";

const cache = new Map<string, Promise<unknown>>();

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const p = fetch(`./data/${path}`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`Couldn't load ${path} (HTTP ${r.status}). Run the pipeline to generate data.`);
      return r.json();
    });
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return cache.get(path) as Promise<T>;
}

export interface Loadable<T> { data: T | null; error: string | null; loading: boolean }

export function useJson<T>(path: string | null): Loadable<T> {
  const [state, set] = useState<Loadable<T>>({ data: null, error: null, loading: !!path });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    set((s) => ({ ...s, loading: true, error: null }));
    load<T>(path).then(
      (d) => alive && set({ data: d, error: null, loading: false }),
      (e: Error) => alive && set({ data: null, error: e.message, loading: false }),
    );
    return () => { alive = false; };
  }, [path]);
  return state;
}

export const useMeta = () => useJson<Meta>("meta.json");
export const usePerformance = () => useJson<Performance>("performance.json");
export const useWeek = (file: string | null) => useJson<WeekData>(file);

export function loadWeek(file: string) { return load<WeekData>(file); }
