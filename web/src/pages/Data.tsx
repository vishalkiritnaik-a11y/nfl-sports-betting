import { useApp } from "../App";
import { Note, Section } from "../components/ui";
import { ago, pct, ZONE_LABEL } from "../lib/format";

export default function DataPage() {
  const { meta } = useApp();
  const M = meta.methodology;
  return (
    <div className="grid gap-5">
      <h1 className="display text-[30px] leading-tight">Data and method</h1>
      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="What's live and what isn't">
          <h3 className="text-sm font-semibold mb-1">Live in this build</h3>
          <ul className="list-disc pl-5 text-sm mb-3">{meta.features.live.map((f) => <li key={f}>{f}</li>)}</ul>
          <h3 className="text-sm font-semibold mb-1">Not available</h3>
          <ul className="list-disc pl-5 text-sm text-muted">{meta.features.unavailable.map((f) => <li key={f}>{f}</li>)}</ul>
          {meta.odds_error && <p className="text-sm mt-2" style={{ color: "var(--warn)" }}>The odds API returned an error on the last run: {meta.odds_error}</p>}
          <p className="text-xs text-muted mt-3">Nothing is filled in by hand or estimated when a source is missing. Missing data shows as unavailable.</p>
        </Section>
        <Section title="Sources and freshness">
          <div className="scroll-x max-h-[360px] overflow-y-auto"><div className="scroll-x"><table className="grid text-[13px]"><thead><tr><th>File</th><th>Source last updated</th><th>Fetched</th></tr></thead>
            <tbody>{meta.sources.map((s) => <tr key={s.file}><td><a className="link" href={s.url} target="_blank" rel="noreferrer">{s.file}</a></td>
              <td className="tnum">{s.source_updated ? `${new Date(s.source_updated).toLocaleString()} (${ago(s.source_updated)})` : "—"}</td><td className="tnum text-muted">{s.fetched ? ago(s.fetched) : "—"}</td></tr>)}</tbody></table></div></div>
          <p className="text-xs text-muted mt-2">nflverse data is CC-BY 4.0 and refreshes nightly, more often on game days. FTN charting is provided through nflverse under FTN's terms. Weather comes from Open-Meteo (CC-BY 4.0). This page was built {new Date(meta.generated).toLocaleString()}, taking {meta.build_seconds}s.</p>
        </Section>
      </div>

      <Section title="Game model">
        <div className="grid lg:grid-cols-[1fr_1.2fr] gap-5 text-sm">
          <div className="grid gap-2 max-w-[75ch]">
            <p>Two transparent models share one set of pre-game features. A ridge regression predicts the home margin and converts it to a win probability with a normal distribution (SD {M.game.sigma_margin.toFixed(1)} points). An L2 logistic regression predicts the winner directly. The published number is their average. A third ridge model predicts total points (SD {M.game.sigma_total.toFixed(1)}).</p>
            <p>Team ratings blend this season with last season, regressed halfway to league average, using shrinkage weights measured in plays (about 5–6 games before the current season dominates). That keeps two hot weeks from overwhelming a season of evidence. Quarterbacks are rated on EPA per dropback over their last ~34 games, decayed and shrunk toward replacement level. A change of starter switches the rating used.</p>
            <p>Context: home field (zero at neutral sites), rest days, travel distance, time-zone shift, Denver altitude, division games, and for totals the observed wind and cold at outdoor venues. Head-to-head history is shown but deliberately not used.</p>
            <p>Trained on {M.game.trained_on} ({M.game.n_train.toLocaleString()} games). Backtests retrain each season on earlier seasons only.</p>
          </div>
          <div className="scroll-x"><div className="scroll-x"><table className="grid text-[13px]"><thead><tr><th>Feature</th><th style={{ textAlign: "right" }}>Margin pts per SD</th><th style={{ textAlign: "right" }}>Logit per SD</th></tr></thead>
            <tbody>{[...M.game.coefficients].sort((a, b) => Math.abs(b.pts_per_sd) - Math.abs(a.pts_per_sd)).map((c) => <tr key={c.feature}><td>{c.label}</td><td className="text-right tnum">{c.pts_per_sd.toFixed(2)}</td><td className="text-right tnum">{c.logit_per_sd.toFixed(3)}</td></tr>)}</tbody></table></div></div>
        </div>
      </Section>

      <Section title="Anytime touchdown model">
        <div className="grid lg:grid-cols-[1fr_1fr] gap-5 text-sm">
          <div className="grid gap-2 max-w-[75ch]">
            <p>Each player's touchdown intensity is built from opportunities, not past touchdown totals. Projected team opportunities by field zone (from the team's projected points and game script) are multiplied by the player's share of each zone. Shares are recency-weighted and shrunk from broad to narrow: carry share informs red-zone share, which informs inside-10 and inside-5 share. That's multiplied again by the league touchdown rate per opportunity.</p>
            <p>Two adjustments follow, both heavily shrunk: the player's finishing rate versus expectation, and the opponent's touchdowns allowed versus expectation, separately for rushing and receiving. Rushing and receiving intensities are added (each play has one ball carrier or target, so nothing is double counted). A logistic calibration layer fit on later seasons then converts the intensity into P(at least one TD), correcting for correlation and over-dispersion rather than assuming independence.</p>
            <p>When a player is ruled out, his shares are redistributed to available teammates in proportion to their own shares. Questionable and doubtful players are never assumed in or out. Both scenarios are computed and you choose with the toggle.</p>
            <p>Calibration layer fit on {M.td.n_calibration.toLocaleString()} walk-forward player-games.</p>
          </div>
          <div>
            <div className="scroll-x"><table className="grid text-[13px]"><thead><tr><th>Opportunity</th><th style={{ textAlign: "right" }}>League TD rate</th></tr></thead>
              <tbody>{Object.entries(M.td.rates_per_opportunity).map(([k, v]) => <tr key={k}><td>{ZONE_LABEL[k] ?? k}</td><td className="text-right tnum">{pct(v, 1)}</td></tr>)}</tbody></table></div>
          </div>
        </div>
      </Section>

      <div className="grid lg:grid-cols-2 gap-5">
        <Section title="Confidence labels">
          <ul className="list-disc pl-5 text-sm grid gap-1 max-w-[75ch]">
            <li><b>Games</b> score points for model agreement (margin vs logistic within 3 pts) and at least 3 current-season games per team. They lose points for an uncertain starting QB, 3 or more key players questionable, doubtful or not practising, and high or uncertain wind. High is 2 or more, Low is below 0.</li>
            <li><b>Players</b> score for 6+ recent games and stable snap share. They lose points for fewer than 3 games, a snap share swinging more than 25 pts, a questionable or doubtful tag, and an uncertain team QB.</li>
            <li>These labels describe how much the inputs could change. They are not calibrated probabilities. Probability and confidence are separate: a 35% player isn't automatically a better bet than a 25% player.</li>
          </ul>
        </Section>
        <Section title="Responsible use">
          <Note>This is an analytical and educational tool. Even a 75% favourite loses one game in four, and long losing runs are normal for any strategy. Never stake money you can't afford to lose, and don't raise stakes to win back losses. If gambling is causing problems, call or text 1-800-GAMBLER (US) for free, confidential help.</Note>
        </Section>
      </div>
    </div>
  );
}
