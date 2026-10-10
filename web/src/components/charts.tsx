import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, ErrorBar, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis, Legend } from "recharts";
import type { CalBin, Contribution, Distribution } from "../types";

const axis = { stroke: "#8a9bb5", fontSize: 12, tickLine: false };
const grid = <CartesianGrid stroke="#24344f" strokeDasharray="0" vertical={false} />;
const tip = { contentStyle: { background: "#1b2b45", border: "1px solid #24344f", borderRadius: 8, color: "#e6ecf5", fontSize: 13 },
  itemStyle: { color: "#e6ecf5" }, labelStyle: { color: "#8a9bb5" } };

export function ContributionChart({ rows, home, away, homeColor, awayColor }: { rows: Contribution[]; home: string; away: string; homeColor: string; awayColor: string }) {
  const data = rows.filter((r) => Math.abs(r.points) >= 0.05).slice(0, 12).map((r) => ({ ...r, pts: +r.points.toFixed(2) })).reverse();
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, data.length * 28 + 40)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        {grid}
        <XAxis type="number" {...axis} tickFormatter={(v) => (v > 0 ? `+${v} ${home}` : v < 0 ? `+${-v} ${away}` : "0")} />
        <YAxis type="category" dataKey="label" width={190} {...axis} />
        <ReferenceLine x={0} stroke="#8a9bb5" />
        <Tooltip {...tip} formatter={(v: number) => [`${v > 0 ? "+" : ""}${v} pts of ${home} margin`, "Contribution"]} />
        <Bar dataKey="pts" radius={3}>
          {data.map((d, i) => <Cell key={i} fill={d.pts >= 0 ? homeColor : awayColor} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MarginHist({ dist, home, away, spread }: { dist: Distribution; home: string; away: string; spread?: number | null }) {
  const data = dist.margin_hist.map((b) => ({ x: (b.lo + b.hi) / 2, label: b.lo >= 0 ? `${home} by ${b.lo}–${b.hi}` : `${away} by ${-b.hi}–${-b.lo}`, p: +(b.p * 100).toFixed(1) }));
  return (
    <ResponsiveContainer width="100%" height={210}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="x" {...axis} tickFormatter={(v) => (v > 0 ? `${home} +${v}` : v < 0 ? `${away} +${-v}` : "0")} />
        <YAxis {...axis} unit="%" width={40} />
        <Tooltip {...tip} labelFormatter={(_, p) => (p?.[0]?.payload?.label ?? "")} formatter={(v: number) => [`${v}%`, "Probability"]} />
        <Bar dataKey="p" radius={[3, 3, 0, 0]}>
          {data.map((d, i) => <Cell key={i} fill={d.x >= 0 ? "#5ab4ff" : "#3d6f9e"} />)}
        </Bar>
        {spread != null && <ReferenceLine x={Math.max(-32.5, Math.min(32.5, Math.floor(spread / 5) * 5 + 2.5))} stroke="#cdae6e" strokeDasharray="4 3" label={{ value: "market line", fill: "#cdae6e", fontSize: 11, position: "top" }} />}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CalibrationChart({ bins, height = 280 }: { bins: CalBin[]; height?: number }) {
  const data = bins.map((b) => ({ pred: +(b.pred * 100).toFixed(1), obs: +(b.obs * 100).toFixed(1), n: b.n,
    err: [+(b.obs * 100 - b.ci90[0] * 100).toFixed(1), +(b.ci90[1] * 100 - b.obs * 100).toFixed(1)] }));
  const max = Math.min(100, Math.ceil(Math.max(...data.map((d) => Math.max(d.pred, d.obs + d.err[1])), 10) / 10) * 10);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 16 }}>
        {grid}
        <XAxis type="number" dataKey="pred" domain={[0, max]} {...axis} unit="%" label={{ value: "Predicted", position: "insideBottom", offset: -8, fill: "#8a9bb5", fontSize: 12 }} />
        <YAxis type="number" domain={[0, max]} {...axis} unit="%" width={44} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: max, y: max }]} stroke="#8a9bb5" strokeDasharray="4 4" />
        <Tooltip {...tip} formatter={(v: number | number[], n: string) => (Array.isArray(v) ? [] : [`${v}%`, n === "obs" ? "Observed" : n])} />
        <Scatter dataKey="obs" fill="#5ab4ff" name="obs">
          <ErrorBar dataKey="err" direction="y" stroke="#5ab4ff" width={4} />
        </Scatter>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function HistoryChart({ rows }: { rows: { run_id: string; p_home: number; market_p_home: number | null }[] }) {
  const data = rows.map((r) => ({ t: new Date(r.run_id).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" }),
    model: +(r.p_home * 100).toFixed(1), market: r.market_p_home != null ? +(r.market_p_home * 100).toFixed(1) : null }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="t" {...axis} />
        <YAxis {...axis} unit="%" width={44} domain={["auto", "auto"]} />
        <Tooltip {...tip} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line dataKey="model" name="Model (home)" stroke="#5ab4ff" strokeWidth={2} dot={{ r: 3 }} />
        <Line dataKey="market" name="Market no-vig (home)" stroke="#cdae6e" strokeWidth={2} dot={{ r: 3 }} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function SeasonLines({ rows }: { rows: { season: number; model?: number; elo?: number; market?: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart data={rows} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="season" {...axis} />
        <YAxis {...axis} domain={["auto", "auto"]} width={52} tickFormatter={(v) => v.toFixed(3)} />
        <Tooltip {...tip} formatter={(v: number) => v.toFixed(4)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line dataKey="model" name="Model" stroke="#5ab4ff" strokeWidth={2} />
        <Line dataKey="elo" name="Elo baseline" stroke="#8a9bb5" strokeWidth={2} strokeDasharray="4 3" />
        <Line dataKey="market" name="Closing market" stroke="#cdae6e" strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function OppBars({ data }: { data: { label: string; v: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={data.length * 26 + 20}>
      <BarChart data={data} layout="vertical" margin={{ left: 4, right: 24, top: 0, bottom: 0 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="label" width={150} {...axis} />
        <Tooltip {...tip} formatter={(v: number) => [v.toFixed(2), "Projected"]} />
        <Bar dataKey="v" fill="#5ab4ff" radius={3} label={{ position: "right", fill: "#e6ecf5", fontSize: 12, formatter: (v: number) => v.toFixed(2) }} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function WeekAccuracy({ rows }: { rows: { week: number; accuracy: number | null; n: number }[] }) {
  const data = rows.map((r) => ({ week: `Wk ${r.week}`, acc: r.accuracy != null ? +(r.accuracy * 100).toFixed(0) : 0, n: r.n }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
        {grid}
        <XAxis dataKey="week" {...axis} />
        <YAxis {...axis} unit="%" domain={[0, 100]} width={40} />
        <ReferenceLine y={50} stroke="#8a9bb5" strokeDasharray="4 4" />
        <Tooltip {...tip} formatter={(v: number, _n, p) => [`${v}% of ${p.payload.n} games`, "Winners picked"]} />
        <Bar dataKey="acc" fill="#5ab4ff" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
