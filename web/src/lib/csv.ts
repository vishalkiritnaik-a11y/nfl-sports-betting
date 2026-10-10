export function toCSV(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    if (v == null) return "";
    const s = typeof v === "number" ? String(Math.round(v * 10000) / 10000) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

export function downloadCSV(name: string, rows: Record<string, unknown>[]) {
  const blob = new Blob([toCSV(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** In the self-contained preview build the host blocks file downloads, so export copies the CSV instead. */
export const SINGLE = import.meta.env.MODE === "single";
export const EXPORT_LABEL = SINGLE ? "Copy CSV" : "Export CSV";

export async function exportCSV(name: string, rows: Record<string, unknown>[]): Promise<string> {
  if (!SINGLE) { downloadCSV(name, rows); return "Downloaded"; }
  try { await navigator.clipboard.writeText(toCSV(rows)); return "Copied to clipboard"; }
  catch { return "Copy blocked here. Use the deployed site to download."; }
}
