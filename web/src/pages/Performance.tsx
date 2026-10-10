import { useState } from "react";
import { usePerformance } from "../lib/data";
import { CalibrationChart, SeasonLines, WeekAccuracy } from "../components/charts";
import { ErrorBox, Loading, Note, Section } from "../components/ui";
import { num, pct, units } from "../lib/format";
import type { Scores } from "../types";

const S = ({ s }: { s?: Scores | null }) => !s ? <>—</> : (
  <><td className="text-right tnum">{s.n.toLocaleString()}</td><td className="text-right tnum">{pct(s.accuracy, 1)}</td>
    <td className="text-right tnum">{s.log_loss.toFixed(4)}</td><td className="text-right tnum">{s.brier.toFixed(4)}</td><td className="text-right tnum">{s.auc?.toFixed(3) ?? "—"}</td></>
);
const head = <tr><th>Forecaster</th><th style={{ textAlign: "right" }}>Games</th><th style={{ textAlign: "right" }}>Winners</th><th style={{ textAlign: "right" }}>Log loss</th><th style={{ textAlign: "right" }}>Brier</th><th style={{ textAlign: "right" }}>AUC</th></tr>;

export default function PerformancePage() {
  const { data: p, error } = usePerformance();
  const [mkt, setMkt] = useState("moneyline");
  if (error) return <ErrorBox msg={error} />;
  if (!p) return <Loading />;
  const G = p.game, T = p.td, P = p.prospective;
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="display text-[30px] leading-tight">Track record</h1>
        <p className="text-muted text-sm max-w-[80ch]">{p.disclaimer} Lower log loss and Brier scores are better. Picking winners and making money are different things: the second requires beating the price, not just the opponent.</p>
      </div>

      <Section title="Logged before kickoff">
        {P.games_logged === 0 ? <Note>No pre-kickoff predictions have been logged yet. The first scheduled run starts the record.</Note> : (
          <div className="grid md:grid-cols-[1fr_1.4fr] gap-5">
            <div className="text-sm grid gap-2 content-start">
              <p>Logging since {P.since ? new Date(P.since).toLocaleDateString() : "—"}: <b>{P.games_logged}</b> games and <b>{P.td_logged}</b> player projections. Graded so far: <b>{P.games_graded}</b> games, <b>{P.td_graded}</b> players.</p>
              {P.game_scores ? (
                <div className="scroll-x"><table className="grid"><thead>{head}</thead><tbody>
                  <tr><td>Model</td><S s={P.game_scores} /></tr>
                  {P.market_scores && <tr><td>Market (no-vig)</td><S s={P.market_scores} /></tr>}
                </tbody></table></div>) : <Note>Scores appear once logged games are final. Too few graded games to judge yet.</Note>}
              {P.td_scores && <p className="text-muted">TD projections: log loss {P.td_scores.log_loss.toFixed(4)}, Brier {P.td_scores.brier.toFixed(4)} over {P.td_scores.n} players.</p>}
            </div>
            <div className="scroll-x max-h-[320px] overflow-y-auto">
              <div className="scroll-x"><table className="grid text-[13px]"><thead><tr><th>Game</th><th style={{ textAlign: "right" }}>Model (home)</th><th style={{ textAlign: "right" }}>Market</th><th>Result</th><th>Logged</th></tr></thead>
                <tbody>{P.recent.map((r) => {
                  const done = r.home_score != null;
                  const right = done && r.home_score !== r.away_score ? (r.p_home > 0.5) === (r.home_score! > r.away_score!) : null;
                  return <tr key={r.game_id}><td>{r.away_team} @ {r.home_team}</td><td className="text-right tnum">{pct(r.p_home, 1)}</td><td className="text-right tnum">{pct(r.market_p_home, 1)}</td>
                    <td style={{ color: right == null ? "var(--muted)" : right ? "var(--pos)" : "var(--neg)" }}>{done ? `${r.away_score}–${r.home_score}${right == null ? "" : right ? ", pick won" : ", pick lost"}` : "pending"}</td>
                    <td className="text-muted text-xs">{new Date(r.run_id).toLocaleString()}</td></tr>;
                })}</tbody></table></div>
            </div>
          </div>)}
      </Section>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title={`Game winners, backtest ${G.period}`}>
          <div className="scroll-x"><table className="grid text-[14px]"><thead>{head}</thead><tbody>
            <tr><td>Model (published)</td><S s={G.overall.model} /></tr>
            <tr><td className="text-muted">Margin component</td><S s={G.overall.margin_component} /></tr>
            <tr><td className="text-muted">Logistic component</td><S s={G.overall.logit_component} /></tr>
            <tr><td>Elo baseline</td><S s={G.overall.elo} /></tr>
            <tr><td>Closing market</td><S s={G.overall.market} /></tr>
          </tbody></table></div>
          <p className="text-xs text-muted mt-2">{G.method} {G.ties_excluded} ties excluded. Margin error: model {num(G.margin_mae, 2)} vs market spread {num(G.market_spread_mae, 2)} points. Total error: model {num(G.total_mae, 2)} vs market {num(G.market_total_mae, 2)}. Correlation with market: {G.corr_with_market.toFixed(2)}.</p>
          <h3 className="text-sm font-semibold mt-4">Log loss by season</h3>
          <SeasonLines rows={G.by_season.map((s) => ({ season: s.season, model: s.model.log_loss, elo: s.elo.log_loss, market: s.market?.log_loss }))} />
        </Section>
        <Section title="Game calibration">
          <CalibrationChart bins={G.calibration} />
          <p className="text-xs text-muted">Each dot: games grouped by predicted home win probability. Bars are 90% intervals. Dots on the diagonal mean the probabilities are honest.</p>
          <div className="scroll-x mt-3"><div className="scroll-x"><table className="grid text-[13px]"><thead><tr><th>Bucket</th><th style={{ textAlign: "right" }}>Games</th><th style={{ textAlign: "right" }}>Predicted</th><th style={{ textAlign: "right" }}>Observed</th><th style={{ textAlign: "right" }}>90% interval</th></tr></thead>
            <tbody>{G.calibration.map((b) => <tr key={b.lo}><td>{pct(b.lo)}–{pct(Math.min(1, b.hi))}</td><td className="text-right tnum">{b.n}</td><td className="text-right tnum">{pct(b.pred, 1)}</td><td className="text-right tnum">{pct(b.obs, 1)}</td><td className="text-right tnum text-muted">{pct(b.ci90[0])}–{pct(b.ci90[1])}</td></tr>)}</tbody></table></div></div>
        </Section>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="This season, week by week">
          {G.current_season_by_week.length ? <WeekAccuracy rows={G.current_season_by_week} /> : <Note>No completed games yet this season.</Note>}
          <p className="text-xs text-muted">Share of winners picked by the walk-forward model (trained only on earlier seasons).</p>
        </Section>
        <Section title="By situation">
          <div className="scroll-x"><table className="grid text-[13.5px]"><thead><tr><th>Segment</th><th style={{ textAlign: "right" }}>Games</th><th style={{ textAlign: "right" }}>Winners</th><th style={{ textAlign: "right" }}>Log loss</th><th style={{ textAlign: "right" }}>Brier</th><th style={{ textAlign: "right" }}>AUC</th></tr></thead>
            <tbody>{G.segments.map((s) => <tr key={s.segment}><td>{s.segment}</td><S s={s} /></tr>)}</tbody></table></div>
        </Section>
      </div>

      <Section title="Simulated betting" aside={<select value={mkt} onChange={(e) => setMkt(e.target.value)} aria-label="Market"><option value="moneyline">Moneyline</option><option value="spread">Spread</option><option value="total">Total</option></select>}>
        <div className="scroll-x"><div className="scroll-x"><table className="grid text-[14px]"><thead><tr><th>Bet when edge ≥</th><th style={{ textAlign: "right" }}>Bets</th><th style={{ textAlign: "right" }}>Won</th><th style={{ textAlign: "right" }}>Win rate (90% CI)</th><th style={{ textAlign: "right" }}>Units</th><th style={{ textAlign: "right" }}>ROI</th></tr></thead>
          <tbody>{G.betting.filter((b) => b.market === mkt).map((b) => (
            <tr key={b.min_edge_pp}><td>{b.min_edge_pp} pts</td><td className="text-right tnum">{b.bets}{b.pushes ? ` (${b.pushes} push)` : ""}</td><td className="text-right tnum">{b.wins}</td>
              <td className="text-right tnum">{pct(b.win_rate, 1)} <span className="text-muted text-xs">{b.win_rate_ci90 ? `${pct(b.win_rate_ci90[0])}–${pct(b.win_rate_ci90[1])}` : ""}</span></td>
              <td className="text-right tnum" style={{ color: b.units >= 0 ? "var(--pos)" : "var(--neg)" }}>{units(b.units)}</td>
              <td className="text-right tnum" style={{ color: (b.roi_pct ?? 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>{b.roi_pct != null ? `${b.roi_pct.toFixed(1)}%` : "—"}</td></tr>))}</tbody></table></div></div>
        <p className="text-xs text-muted mt-2">{G.betting_note} Every bet the rule would have placed is counted, including the losers.</p>
      </Section>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title={`Anytime TD model, backtest ${T.period}`}>
          <dl className="grid grid-cols-3 gap-3 tnum text-sm mb-3">
            <div><dt className="text-xs text-muted">Player-games</dt><dd className="text-[18px]">{T.overall.n.toLocaleString()}</dd></div>
            <div><dt className="text-xs text-muted">Log loss (vs base rate)</dt><dd className="text-[18px]">{T.overall.log_loss.toFixed(4)} <span className="text-xs text-muted">({T.overall.base_rate_log_loss.toFixed(4)})</span></dd></div>
            <div><dt className="text-xs text-muted">AUC</dt><dd className="text-[18px]">{T.overall.auc?.toFixed(3)}</dd></div>
          </dl>
          <CalibrationChart bins={T.calibration} height={250} />
          <p className="text-xs text-muted">{T.method}</p>
          <div className="scroll-x"><table className="grid text-[13px] mt-3"><thead><tr><th>Rule</th><th style={{ textAlign: "right" }}>Players</th><th style={{ textAlign: "right" }}>Avg predicted</th><th style={{ textAlign: "right" }}>Actually scored</th></tr></thead>
            <tbody>{T.top_picks.map((r) => <tr key={r.rule}><td>{r.rule}</td><td className="text-right tnum">{r.n}</td><td className="text-right tnum">{pct(r.avg_pred, 1)}</td><td className="text-right tnum">{pct(r.hit_rate, 1)}</td></tr>)}</tbody></table></div>
        </Section>
        <Section title="TD calibration by position">
          <div className="scroll-x"><table className="grid text-[13.5px]"><thead><tr><th>Position</th><th style={{ textAlign: "right" }}>Players</th><th style={{ textAlign: "right" }}>Avg predicted</th><th style={{ textAlign: "right" }}>Scored</th><th style={{ textAlign: "right" }}>Log loss</th><th style={{ textAlign: "right" }}>AUC</th></tr></thead>
            <tbody>{T.by_position.map((r) => <tr key={r.position}><td>{r.position}</td><td className="text-right tnum">{r.n.toLocaleString()}</td><td className="text-right tnum">{pct(r.pred_mean, 1)}</td><td className="text-right tnum">{pct(r.obs_mean, 1)}</td><td className="text-right tnum">{r.log_loss.toFixed(4)}</td><td className="text-right tnum">{r.auc?.toFixed(3)}</td></tr>)}</tbody></table></div>
          <div className="grid sm:grid-cols-2 gap-3 mt-4">
            {T.by_position.map((r) => (
              <div key={r.position}><p className="text-xs text-muted mb-1">{r.position} by probability range</p>
                <div className="scroll-x"><table className="grid text-[12.5px]"><tbody>{r.calibration.map((b) => <tr key={b.lo}><td>{pct(b.lo)}–{pct(Math.min(1, b.hi))}</td><td className="text-right tnum">{b.n}</td><td className="text-right tnum">{pct(b.pred, 1)}</td><td className="text-right tnum">{pct(b.obs, 1)}</td></tr>)}</tbody></table></div>
              </div>))}
          </div>
          <p className="text-xs text-muted mt-3">{T.market_note}</p>
        </Section>
      </div>
    </div>
  );
}
