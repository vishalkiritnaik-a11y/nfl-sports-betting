"""Model evaluation: walk-forward backtests, calibration, market comparison,
simulated betting, and the prospective (pre-kickoff logged) track record."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.metrics import roc_auc_score

from . import db as DB
from . import odds as O


def wilson(k: int, n: int, z: float = 1.645) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def calib_bins(p: np.ndarray, y: np.ndarray, edges) -> list[dict]:
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if n == 0:
            continue
        k = int(y[m].sum())
        out.append({"lo": lo, "hi": hi, "n": n, "pred": float(p[m].mean()), "obs": k / n, "ci90": wilson(k, n)})
    return out


def scores(p, y) -> dict:
    p, y = np.asarray(p, float), np.asarray(y, int)
    return {"n": int(len(y)), "log_loss": O.log_loss(p, y), "brier": O.brier(p, y),
            "accuracy": float(((p > 0.5) == (y == 1)).mean()) if len(y) else None,
            "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None}


def _bet(p_model, odds_a, odds_b, won, push=None):
    """Return (stake, profit) for a 1-unit bet on side A, or None if no line."""
    if pd.isna(odds_a) or pd.isna(odds_b):
        return None
    dec = O.american_to_decimal(odds_a)
    if push is not None and push:
        return 0.0
    return dec - 1 if won else -1.0


def betting_sim(bt: pd.DataFrame, sig_m: float, sig_t: float) -> list[dict]:
    res = []
    for market in ("moneyline", "spread", "total"):
        for th in (1.0, 2.0, 3.0, 5.0, 8.0):
            n = wins = pushes = 0
            profit = 0.0
            for r in bt.itertuples(index=False):
                if market == "moneyline":
                    if pd.isna(r.home_moneyline) or pd.isna(r.away_moneyline) or r.margin == 0:
                        continue
                    nv = O.remove_vig_proportional([O.american_to_implied(r.home_moneyline), O.american_to_implied(r.away_moneyline)])
                    cands = [(r.p_home - nv[0], r.home_moneyline, r.margin > 0), (1 - r.p_home - nv[1], r.away_moneyline, r.margin < 0)]
                elif market == "spread":
                    if pd.isna(r.spread_line) or pd.isna(r.home_spread_odds) or pd.isna(r.away_spread_odds):
                        continue
                    ph = 1 - norm.cdf((r.spread_line - r.exp_margin) / sig_m)
                    nv = O.remove_vig_proportional([O.american_to_implied(r.home_spread_odds), O.american_to_implied(r.away_spread_odds)])
                    diff = r.margin - r.spread_line
                    cands = [(ph - nv[0], r.home_spread_odds, diff > 0, diff == 0), (1 - ph - nv[1], r.away_spread_odds, diff < 0, diff == 0)]
                else:
                    if pd.isna(r.total_line) or pd.isna(r.over_odds) or pd.isna(r.under_odds):
                        continue
                    po = 1 - norm.cdf((r.total_line - r.exp_total) / sig_t)
                    nv = O.remove_vig_proportional([O.american_to_implied(r.over_odds), O.american_to_implied(r.under_odds)])
                    diff = r.total - r.total_line
                    cands = [(po - nv[0], r.over_odds, diff > 0, diff == 0), (1 - po - nv[1], r.under_odds, diff < 0, diff == 0)]
                best = max(cands, key=lambda c: c[0])
                if best[0] * 100 < th:
                    continue
                n += 1
                if len(best) > 3 and best[3]:
                    pushes += 1
                    continue
                dec = O.american_to_decimal(best[1])
                if best[2]:
                    wins += 1; profit += dec - 1
                else:
                    profit -= 1
            graded = n - pushes
            res.append({"market": market, "min_edge_pp": th, "bets": n, "pushes": pushes, "wins": wins,
                        "win_rate": wins / graded if graded else None, "units": profit,
                        "roi_pct": 100 * profit / n if n else None,
                        "win_rate_ci90": wilson(wins, graded) if graded else None})
    return res


def performance(gf, gp_bt, games, td_bt, db, live, td_live, season) -> dict:
    cols = ["game_id", "season", "week", "home_team", "away_team", "home_moneyline", "away_moneyline", "spread_line",
            "home_spread_odds", "away_spread_odds", "total_line", "over_odds", "under_odds", "roof", "wind", "location"]
    bt = gp_bt.merge(gf[["game_id", "margin", "total", "elo_prob", "played"]], on="game_id").merge(games[cols], on="game_id")
    bt = bt[bt.played].copy()
    dec = bt[bt.margin != 0].copy()
    y = (dec.margin > 0).astype(int).values
    has_m = dec.home_moneyline.notna() & dec.away_moneyline.notna()
    dec["mkt_p"] = np.nan
    dec.loc[has_m, "mkt_p"] = [O.remove_vig_proportional([O.american_to_implied(a), O.american_to_implied(b)])[0]
                               for a, b in zip(dec.home_moneyline[has_m], dec.away_moneyline[has_m])]
    by_season = []
    for s, d in dec.groupby("season"):
        yy = (d.margin > 0).astype(int)
        m = d.mkt_p.notna()
        by_season.append({"season": int(s), "model": scores(d.p_home, yy), "elo": scores(d.elo_prob, yy),
                          "market": scores(d.mkt_p[m], yy[m]) if m.any() else None,
                          "model_same_games": scores(d.p_home[m], yy[m]) if m.any() else None})
    by_week_cur = []
    for w, d in dec[dec.season == season].groupby("week"):
        yy = (d.margin > 0).astype(int)
        by_week_cur.append({"week": int(w), **scores(d.p_home, yy), "correct": int(((d.p_home > 0.5) == (yy == 1)).sum())})
    fav_home = dec.p_home >= 0.5
    windy = (dec.roof.isin(["outdoors", "open"])) & (dec.wind >= 15)
    seg = []
    for name, m in (("Model favours home team", fav_home), ("Model favours away team", ~fav_home),
                    ("Neutral site", dec.location == "Neutral"), ("Outdoor, wind >= 15 mph", windy),
                    ("Outdoor, wind < 15 mph", dec.roof.isin(["outdoors", "open"]) & ~windy),
                    ("Indoor / closed roof", dec.roof.isin(["dome", "closed"]))):
        d = dec[m]
        if len(d) >= 10:
            yy = (d.margin > 0).astype(int)
            seg.append({"segment": name, **scores(d.p_home, yy)})
    mm = dec.mkt_p.notna()
    game = {
        "period": f"{int(dec.season.min())}-{int(dec.season.max())}",
        "method": "Walk-forward: for each season, models are trained only on earlier seasons; features use only games before kickoff.",
        "overall": {"model": scores(dec.p_home, y), "logit_component": scores(dec.p_logit_model, y),
                    "margin_component": scores(dec.p_margin_model, y), "elo": scores(dec.elo_prob, y),
                    "market": scores(dec.mkt_p[mm], y[mm.values]), "model_same_games": scores(dec.p_home[mm], y[mm.values])},
        "by_season": by_season, "current_season_by_week": by_week_cur, "segments": seg,
        "calibration": calib_bins(dec.p_home.values, y, [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001]),
        "margin_mae": float(np.mean(np.abs(bt.exp_margin - bt.margin))),
        "market_spread_mae": float(np.mean(np.abs(bt.spread_line - bt.margin)[bt.spread_line.notna()])),
        "total_mae": float(np.mean(np.abs(bt.exp_total - bt.total))),
        "market_total_mae": float(np.mean(np.abs(bt.total_line - bt.total)[bt.total_line.notna()])),
        "corr_with_market": float(np.corrcoef(dec.p_home[mm], dec.mkt_p[mm])[0, 1]),
        "ties_excluded": int((bt.margin == 0).sum()),
        "betting": betting_sim(bt, live.sigma_margin, live.sigma_total),
        "betting_note": ("Simulated at nflverse closing consensus prices, 1 unit flat per bet, best side only. Closing lines are the "
                         "hardest prices to beat; real results depend on the price you actually get. Past simulated ROI does not "
                         "predict future returns."),
    }
    tdd = td_bt
    yt = tdd.y.values
    td = {
        "period": f"{int(tdd.season.min())}-{int(tdd.season.max())}",
        "method": ("Walk-forward by season: TD rates, the team-opportunity model and the calibration layer are fit on earlier seasons "
                   "only. Population: every QB/RB/WR/TE who took an offensive snap (inactive players are excluded, as at kickoff)."),
        "overall": {**scores(tdd.p, yt), "base_rate": float(yt.mean()),
                    "base_rate_log_loss": O.log_loss([yt.mean()] * len(yt), yt)},
        "calibration": calib_bins(tdd.p.values, yt, [0, .05, .1, .15, .2, .25, .3, .35, .4, .5, 1.0001]),
        "by_position": [{"position": p_, **scores(d.p, d.y), "pred_mean": float(d.p.mean()), "obs_mean": float(d.y.mean()),
                         "calibration": calib_bins(d.p.values, d.y.values, [0, .1, .2, .3, .4, 1.0001])}
                        for p_, d in tdd.groupby("position")],
        "by_season": [{"season": int(s), **scores(d.p, d.y)} for s, d in tdd.groupby("season")],
        "top_picks": [{"rule": f"p >= {th:.0%}", "n": int((tdd.p >= th).sum()),
                       "hit_rate": float(tdd.y[tdd.p >= th].mean()) if (tdd.p >= th).any() else None,
                       "avg_pred": float(tdd.p[tdd.p >= th].mean()) if (tdd.p >= th).any() else None}
                      for th in (0.3, 0.4, 0.5)],
        "market_note": "No historical anytime-TD odds are available in free data, so TD model vs market and TD betting ROI are not evaluated.",
    }
    # prospective
    pg = pd.DataFrame(DB.last_pregame_games(db))
    pros = {"games_logged": 0, "games_graded": 0, "td_logged": 0, "td_graded": 0, "since": None, "recent": []}
    if len(pg):
        pros["games_logged"] = int(len(pg))
        pros["since"] = pg.run_id.min()
        g = pg[pg.home_score.notna() & (pg.home_score != pg.away_score)]
        pros["games_graded"] = int(len(g))
        if len(g):
            yy = (g.home_score > g.away_score).astype(int)
            pros["game_scores"] = scores(g.p_home, yy)
            mk = g.market_p_home.notna()
            if mk.any():
                pros["market_scores"] = scores(g.market_p_home[mk], yy[mk])
                pros["model_same_games"] = scores(g.p_home[mk], yy[mk])
        pros["recent"] = [{k: r[k] for k in ("game_id", "run_id", "p_home", "market_p_home", "home_team", "away_team", "home_score", "away_score", "confidence")}
                          for r in pg.sort_values("kickoff_utc", ascending=False).head(60).to_dict("records")]
    tp = pd.DataFrame(DB.last_pregame_tds(db))
    if len(tp):
        pros["td_logged"] = int(len(tp))
        t = tp[tp.scored.notna()]
        pros["td_graded"] = int(len(t))
        if len(t) and t.scored.nunique() > 1:
            pros["td_scores"] = scores(t.p_anytime, t.scored.astype(int))
            pros["td_calibration"] = calib_bins(t.p_anytime.values, t.scored.astype(int).values, [0, .1, .2, .3, .4, 1.0001])
    return {"game": game, "td": td, "prospective": pros,
            "disclaimer": ("Backtests are out-of-sample but retrospective. The prospective log records every pre-kickoff prediction "
                           "this pipeline publishes and is never edited; losing predictions stay in the record.")}
