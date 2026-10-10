export const pct = (p: number | null | undefined, d = 0) => (p == null || Number.isNaN(p) ? "—" : `${(p * 100).toFixed(d)}%`);
export const pp = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(d)} pts`);
export const num = (x: number | null | undefined, d = 1) => (x == null || Number.isNaN(x) ? "—" : x.toFixed(d));
export const signed = (x: number | null | undefined, d = 1) => (x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(d)}`);
export const units = (x: number | null | undefined) => (x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(2)}u`);

export function kickoffLocal(iso: string): { day: string; time: string; date: Date } {
  const d = new Date(iso);
  return {
    date: d,
    day: d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
    time: d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
  };
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 0) return "just now";
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export function slotOf(g: { weekday: string; gametime_et: string }): string {
  const h = parseInt(g.gametime_et?.split(":")[0] ?? "13", 10);
  if (g.weekday === "Sunday") return h < 12 ? "Sunday morning" : h < 16 ? "Sunday early" : h < 19 ? "Sunday late" : "Sunday night";
  return g.weekday;
}

export const ZONE_LABEL: Record<string, string> = {
  c_i5: "Carries inside 5", c_6_10: "Carries 6–10", c_11_20: "Carries 11–20", c_out: "Carries outside 20",
  t_ez: "End-zone targets", t_rz: "Other red-zone targets", t_out: "Targets outside 20",
};

function lum(hex: string): number {
  const h = hex.replace("#", "");
  if (h.length < 6) return 0.5;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function lighten(hex: string, amt: number): string {
  const h = hex.replace("#", "");
  const c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).map((v) => Math.round(v + (255 - v) * amt));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
/** Team colour that stays visible on the navy background: picks the brighter of the two brand colours, lightening if needed. */
export function visibleColor(c1?: string, c2?: string): string {
  const cands = [c1, c2].filter((c): c is string => !!c && /^#?[0-9a-f]{6}$/i.test(c.replace("#", ""))).map((c) => (c.startsWith("#") ? c : `#${c}`));
  if (!cands.length) return "#8a9bb5";
  let best = cands[0];
  if (lum(best) < 0.04 && cands[1] && lum(cands[1]) > lum(best) && lum(cands[1]) < 0.8) best = cands[1];
  let i = 0;
  while (lum(best) < 0.06 && i++ < 6) best = lighten(best, 0.18);
  return best;
}
