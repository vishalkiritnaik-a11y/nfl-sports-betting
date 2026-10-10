import type { TDPlayer, TeamInfo } from "../types";
import { ConfidenceTag, Edge, SortTable, StatusTag, Star, TeamMark, type Col } from "./ui";
import { OppBars } from "./charts";
import { num, pct, ZONE_LABEL } from "../lib/format";
import { fmtAmerican, probToAmerican } from "../lib/odds";
import { tdEV, tdP } from "../lib/derive";
import { useSettings } from "../lib/store";

const CONF = { High: 3, Medium: 2, Low: 1, "n/a": 0 } as const;

export function tdExportRows(rows: TDPlayer[], withoutUncertain: boolean) {
  return rows.map((t) => {
    const p = tdP(t, withoutUncertain);
    return {
      player: t.name, team: t.team, opp: t.opp, position: t.position, status: t.status, p_anytime_td: p,
      fair_american: p && p > 0 && p < 1 ? probToAmerican(p) : null, p_first_td_approx: t.p_first_td_approx ?? null,
      rush_td_lambda: t.lam_rush, rec_td_lambda: t.lam_rec, market_odds: t.market?.odds ?? null, market_book: t.market?.book ?? null,
      edge_pp: t.market && p != null ? (p - t.market.raw_implied) * 100 : null, ev_per_unit: tdEV(t, p),
      confidence: t.confidence?.label ?? null, season_tds: t.recent?.season_tds ?? null, last3_tds: t.recent?.last3 ?? null,
      last5_tds: t.recent?.last5 ?? null, last10_tds: t.recent?.last10 ?? null, scored: t.scored ?? null, game_id: t.game_id,
    };
  });
}

function Detail({ t, p }: { t: TDPlayer; p: number | null }) {
  const eo = t.exp_opps ?? {};
  const bars = Object.entries(eo).filter(([, v]) => v >= 0.02).map(([k, v]) => ({ label: ZONE_LABEL[k] ?? k, v }));
  const s = t.season ?? {}, r = t.recent, u = t.usage ?? {};
  return (
    <div className="grid md:grid-cols-[1.2fr_1fr_1fr] gap-5 py-3 px-1 text-[13.5px]">
      <div>
        <p className="mb-2">{t.why ?? "Walk-forward backtest projection."}</p>
        {bars.length > 0 && <><p className="text-xs text-muted mb-1">Projected opportunities this game</p><OppBars data={bars} /></>}
        <p className="text-xs text-muted mt-2">
          TD pathway: {pct(t.lam_rush / Math.max(1e-6, t.lam_rush + t.lam_rec))} rushing, {pct(t.lam_rec / Math.max(1e-6, t.lam_rush + t.lam_rec))} receiving.
          {t.p_first_td_approx != null && <> Approximate first-TD probability {pct(t.p_first_td_approx, 1)}: a different, much less likely bet than anytime.</>}
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 content-start tnum">
        <dt className="text-muted">Season TDs</dt><dd>{r?.season_tds ?? s.season_tds ?? "—"}</dd>
        <dt className="text-muted">TDs last 3 / 5 / 10</dt><dd>{r ? `${r.last3} / ${r.last5} / ${r.last10}` : "—"}</dd>
        <dt className="text-muted">Carries inside 5 / 10</dt><dd>{r ? `${r.season_i5_carries} / ${r.season_i10_carries}` : "—"}</dd>
        <dt className="text-muted">Red-zone / end-zone tgts</dt><dd>{r ? `${r.season_rz_targets} / ${r.season_ez_targets}` : "—"}</dd>
        <dt className="text-muted">Carries / targets per game</dt><dd>{num(s.carries_pg)} / {num(s.targets_pg)}</dd>
        <dt className="text-muted">Rec. / yards per game</dt><dd>{num(s.receptions_pg)} / {num((s.rush_yds_pg ?? 0) + (s.rec_yds_pg ?? 0), 0)}</dd>
        <dt className="text-muted">Target share</dt><dd>{pct(u.share_targets ?? s.target_share ?? null)}</dd>
        <dt className="text-muted">Carry share</dt><dd>{pct(u.share_carries ?? null)}</dd>
        <dt className="text-muted">Inside-10 carry share</dt><dd>{pct(u.share_i10_carries ?? null)}</dd>
        <dt className="text-muted">Snap share, last 3</dt><dd>{t.snap_pct_last3?.length ? t.snap_pct_last3.map((x) => pct(x)).join(", ") : "—"}</dd>
      </dl>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 content-start tnum">
        <dt className="text-muted">Team projected pts</dt><dd>{num(t.team_exp_points)}</dd>
        <dt className="text-muted">Projected game script</dt><dd>{t.team_exp_margin != null ? `${t.team_exp_margin >= 0 ? "leads" : "trails"} by ${Math.abs(t.team_exp_margin).toFixed(1)}` : "—"}</dd>
        <dt className="text-muted">{t.opp} TDs allowed to {t.position}s</dt><dd>{t.opp_vs_pos ? `${t.opp_vs_pos.td_pg.toFixed(2)}/g (rank ${t.opp_vs_pos.rank} most)` : "—"}</dd>
        <dt className="text-muted">Opponent adj. rush / rec</dt><dd>{t.opp_mult ? `${t.opp_mult.rush.toFixed(2)}x / ${t.opp_mult.rec.toFixed(2)}x` : "—"}</dd>
        <dt className="text-muted">Finishing adj. (shrunk)</dt><dd>{t.finishing_mult ? `${t.finishing_mult.toFixed(2)}x` : "—"}</dd>
        <dt className="text-muted">Uncalibrated Poisson</dt><dd>{pct(t.p_raw_poisson ?? null, 1)}</dd>
        <dt className="text-muted">If questionable teammates sit</dt><dd>{t.p_if_uncertain_out != null ? pct(t.p_if_uncertain_out, 1) : "—"}</dd>
        <dt className="text-muted">Fair odds</dt><dd>{p ? fmtAmerican(probToAmerican(p)) : "—"}</dd>
        <dt className="text-muted">Confidence</dt><dd><ConfidenceTag c={t.confidence} /></dd>
        {t.confidence?.reasons?.length ? <dd className="col-span-2 text-xs text-muted">{t.confidence.reasons.join(". ")}.</dd> : null}
        {t.market && <dd className="col-span-2 text-xs text-muted">{t.market.note}</dd>}
      </dl>
    </div>
  );
}

export default function TDTable({ rows, teams, showGame = true }: { rows: TDPlayer[]; teams: Record<string, TeamInfo>; showGame?: boolean }) {
  const { withoutUncertain, watch, togglePlayer } = useSettings();
  const anyMarket = rows.some((t) => t.market);
  const anyResult = rows.some((t) => t.scored != null);
  const cols: Col<TDPlayer>[] = [
    { key: "w", label: <span className="sr-only">Watch</span>, render: (t) => <Star on={watch.players.includes(t.player_id)} onClick={() => togglePlayer(t.player_id)} label={t.name} /> },
    { key: "name", label: "Player", sort: (t) => t.name, render: (t) => (
      <span className="flex items-center gap-2 min-w-[180px]">
        <TeamMark team={t.team} info={teams[t.team]} size={20} />
        <span><span className="font-medium">{t.name}</span> <span className="text-muted text-xs">{t.position}</span></span>
        <StatusTag s={t.status} />
      </span>) },
    ...(showGame ? [{ key: "opp", label: "Opp", sort: (t: TDPlayer) => t.opp, render: (t: TDPlayer) => <span className="text-muted">{t.opp}</span> }] : []),
    { key: "p", label: "Anytime TD", align: "right", sort: (t) => tdP(t, withoutUncertain) ?? -1,
      render: (t) => { const p = tdP(t, withoutUncertain); return p == null ? <span className="text-muted text-xs">sits in this scenario</span> : <span className="font-semibold">{pct(p, 1)}</span>; } },
    { key: "fair", label: "Fair odds", align: "right", title: "Odds at which the bet breaks even if the model is right",
      sort: (t) => tdP(t, withoutUncertain) ?? -1, render: (t) => { const p = tdP(t, withoutUncertain); return p && p < 1 ? fmtAmerican(probToAmerican(p)) : "—"; } },
    { key: "path", label: "Rush / rec", align: "right", sort: (t) => t.lam_rush / Math.max(1e-6, t.lam_rush + t.lam_rec),
      render: (t) => <span className="text-muted">{pct(t.lam_rush / Math.max(1e-6, t.lam_rush + t.lam_rec))} / {pct(t.lam_rec / Math.max(1e-6, t.lam_rush + t.lam_rec))}</span> },
    { key: "l5", label: "TDs last 5", align: "right", sort: (t) => t.recent?.last5 ?? null, render: (t) => t.recent?.last5 ?? "—" },
    { key: "season", label: "Season TDs", align: "right", sort: (t) => t.recent?.season_tds ?? null, render: (t) => t.recent?.season_tds ?? "—" },
    ...(anyMarket ? [
      { key: "odds", label: "Book odds", align: "right" as const, sort: (t: TDPlayer) => t.market?.odds ?? null, render: (t: TDPlayer) => t.market ? `${fmtAmerican(t.market.odds)}` : "—" },
      { key: "edge", label: "Edge (pts)", align: "right" as const, sort: (t: TDPlayer) => { const p = tdP(t, withoutUncertain); return t.market && p != null ? (p - t.market.raw_implied) * 100 : null; },
        render: (t: TDPlayer) => { const p = tdP(t, withoutUncertain); return <Edge v={t.market && p != null ? (p - t.market.raw_implied) * 100 : null} />; } },
      { key: "ev", label: "EV / unit", align: "right" as const, sort: (t: TDPlayer) => tdEV(t, tdP(t, withoutUncertain)), render: (t: TDPlayer) => { const v = tdEV(t, tdP(t, withoutUncertain)); return v == null ? "—" : <Edge v={v} />; } },
    ] : []),
    { key: "conf", label: "Confidence", sort: (t) => CONF[t.confidence?.label ?? "n/a"], render: (t) => <ConfidenceTag c={t.confidence} /> },
    ...(anyResult ? [{ key: "res", label: "Result", sort: (t: TDPlayer) => t.scored ?? null, render: (t: TDPlayer) => t.scored == null ? "—" : <span style={{ color: t.scored ? "var(--pos)" : "var(--muted)" }}>{t.scored ? "Scored" : "No TD"}</span> }] : []),
  ];
  return <SortTable rows={rows} cols={cols} initial="p" rowKey={(t) => t.player_id + t.game_id} expand={(t) => <Detail t={t} p={tdP(t, withoutUncertain)} />}
    empty="No players match these filters." />;
}
