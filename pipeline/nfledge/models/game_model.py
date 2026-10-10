"""Explainable game model.

Two independent models on the same leak-free features:
  A. Ridge regression on home margin -> P(home win) = Phi(mu / sigma)
  B. L2 logistic regression on home win
The published probability is their average; their disagreement feeds the
confidence rating. A separate ridge model predicts total points. Feature
contributions are reported in points of margin (coef * (x - training mean)).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from .. import features as F
from . import elo as elo_mod

MARGIN_FEATURES = {
    "elo_pts": "Elo rating gap (pts)",
    "home_field": "Home field",
    "net_epa": "Net EPA/play matchup",
    "net_pass_epa": "Pass offense vs pass defense",
    "net_rush_epa": "Rush offense vs rush defense",
    "net_success": "Success-rate matchup",
    "net_st": "Special teams EPA",
    "net_to": "Turnover tendencies",
    "net_pressure": "Pass rush vs protection",
    "net_rz": "Red-zone TD rate",
    "qb_diff": "Starting QB EPA/dropback",
    "qb_change_home": "Home QB change",
    "qb_change_away": "Away QB change",
    "rest_diff": "Rest advantage (days)",
    "travel_diff_1000km": "Travel burden (1000 km)",
    "tz_diff": "Time-zone shift",
    "altitude_home": "Altitude (Denver)",
    "div_game": "Division game",
}
TOTAL_FEATURES = {
    "sum_points": "Points for/against blend",
    "sum_epa": "Combined offense vs defense EPA",
    "sum_pace": "Combined plays per game",
    "sum_explosive": "Explosive-play rates",
    "sum_rz": "Red-zone TD rates",
    "qb_sum": "Both QBs' EPA/dropback",
    "outdoor": "Outdoor venue",
    "wind_excess": "Wind above 10 mph",
    "cold_excess": "Temperature below 40F",
    "net_pts_abs": "Mismatch size",
}


class QBRater:
    def __init__(self, qb_games: pd.DataFrame, games: pd.DataFrame):
        q = qb_games.merge(games[["game_id", "gameday"]], on="game_id")
        self.by_qb = {k: v.sort_values("gameday") for k, v in q.groupby("qb_id")}

    def rate(self, qb_id, before: str) -> tuple[float, int]:
        if not isinstance(qb_id, str) or qb_id not in self.by_qb:
            return F.QB_REPLACEMENT_EPA, 0
        q = self.by_qb[qb_id]
        q = q[q.gameday < before].tail(34)
        if q.empty:
            return F.QB_REPLACEMENT_EPA, 0
        w = 0.97 ** np.arange(len(q))[::-1]
        db, epa = float((q.db * w).sum()), float((q.epa * w).sum())
        return (epa + F.K_DROPBACKS_QB * F.QB_REPLACEMENT_EPA) / (db + F.K_DROPBACKS_QB), int(q.db.sum())


def previous_starter(games: pd.DataFrame, team: str, before: str):
    h = games[(games.home_team == team) & (games.gameday < before) & games.home_score.notna()][["gameday", "home_qb_id"]].rename(columns={"home_qb_id": "q"})
    a = games[(games.away_team == team) & (games.gameday < before) & games.away_score.notna()][["gameday", "away_qb_id"]].rename(columns={"away_qb_id": "q"})
    x = pd.concat([h, a]).sort_values("gameday")
    return x.q.iloc[-1] if len(x) else None


def game_features(g: pd.Series, games: pd.DataFrame, rater: F.TeamRater, qbr: QBRater, elo_row: dict,
                  venue_cache: dict, qb_override: dict | None = None) -> dict:
    """All features for one game, home perspective. ``qb_override`` = {"home": qb_id, "away": qb_id}."""
    before = g.gameday
    H = rater.rate(g.home_team, g.season, before)
    A = rater.rate(g.away_team, g.season, before)
    ctx = F.context_features(g, games, venue_cache)
    qb = {}
    for side in ("home", "away"):
        qid = (qb_override or {}).get(side, g.get(f"{side}_qb_id"))
        prev = previous_starter(games, g[f"{side}_team"], before)
        if not isinstance(qid, str):  # future game with no listed starter: assume last starter
            qid = prev
        r, n = qbr.rate(qid, before)
        qb[side] = {"id": qid, "epa_db": r, "dropbacks": n,
                    "changed": int(isinstance(prev, str) and isinstance(qid, str) and prev != qid)}
    x = {
        "elo_pts": elo_row["elo_diff_nohfa"] / elo_mod.ELO_PER_POINT,
        "home_field": ctx["home_field"],
        "net_epa": (H["o_epa_play"] + A["d_epa_play"]) - (A["o_epa_play"] + H["d_epa_play"]),
        "net_pass_epa": (H["o_pass_epa"] + A["d_pass_epa"]) - (A["o_pass_epa"] + H["d_pass_epa"]),
        "net_rush_epa": (H["o_rush_epa"] + A["d_rush_epa"]) - (A["o_rush_epa"] + H["d_rush_epa"]),
        "net_success": (H["o_success"] + A["d_success"]) - (A["o_success"] + H["d_success"]),
        "net_st": H["o_st_epa"] - A["o_st_epa"],
        "net_to": (A["o_to_rate"] + H["d_to_rate"]) - (H["o_to_rate"] + A["d_to_rate"]),
        "net_pressure": (H["d_pressure_rate"] + A["o_pressure_rate"]) - (A["d_pressure_rate"] + H["o_pressure_rate"]),
        "net_rz": (H["o_rz_td"] + A["d_rz_td"]) - (A["o_rz_td"] + H["d_rz_td"]),
        "qb_diff": qb["home"]["epa_db"] - qb["away"]["epa_db"],
        "qb_change_home": qb["home"]["changed"],
        "qb_change_away": qb["away"]["changed"],
        "rest_diff": ctx["rest_diff"],
        "travel_diff_1000km": ctx["travel_diff_1000km"],
        "tz_diff": ctx["tz_diff"],
        "altitude_home": ctx["altitude_home"],
        "div_game": ctx["div_game"],
        # total-model features
        "sum_points": H["o_points"] + A["d_points"] + A["o_points"] + H["d_points"],
        "sum_epa": H["o_epa_play"] + A["d_epa_play"] + A["o_epa_play"] + H["d_epa_play"],
        "sum_pace": H["o_plays_pg"] + A["o_plays_pg"] + H["d_plays_pg"] + A["d_plays_pg"],
        "sum_explosive": H["o_explosive"] + A["d_explosive"] + A["o_explosive"] + H["d_explosive"],
        "sum_rz": H["o_rz_td"] + A["d_rz_td"] + A["o_rz_td"] + H["d_rz_td"],
        "qb_sum": qb["home"]["epa_db"] + qb["away"]["epa_db"],
        "outdoor": ctx["outdoor"],
        "wind_excess": ctx["wind_excess"],
        "cold_excess": ctx["cold_excess"],
    }
    x["net_pts_abs"] = abs((H["o_points"] + A["d_points"]) - (A["o_points"] + H["d_points"])) / 2
    meta = {"home_ratings": H, "away_ratings": A, "ctx": ctx, "qb": qb}
    return {"x": x, "meta": meta}


@dataclass
class GameModel:
    margin: Ridge = None
    total: Ridge = None
    logit: LogisticRegression = None
    sc_m: StandardScaler = None
    sc_t: StandardScaler = None
    sigma_margin: float = 13.5
    sigma_total: float = 13.0
    mean_m: dict = field(default_factory=dict)
    mean_t: dict = field(default_factory=dict)
    n_train: int = 0
    train_span: str = ""

    def fit(self, X: pd.DataFrame, margin: np.ndarray, total: np.ndarray, span: str = ""):
        mf, tf = list(MARGIN_FEATURES), list(TOTAL_FEATURES)
        self.sc_m = StandardScaler().fit(X[mf])
        self.sc_t = StandardScaler().fit(X[tf])
        Xm, Xt = self.sc_m.transform(X[mf]), self.sc_t.transform(X[tf])
        self.margin = Ridge(alpha=25.0).fit(Xm, margin)
        self.total = Ridge(alpha=25.0).fit(Xt, total)
        y = (margin > 0).astype(int)
        keep = margin != 0
        self.logit = LogisticRegression(C=0.05, max_iter=2000).fit(Xm[keep], y[keep])
        rm = margin - self.margin.predict(Xm)
        rt = total - self.total.predict(Xt)
        self.sigma_margin = float(np.sqrt(np.mean(rm ** 2)))
        self.sigma_total = float(np.sqrt(np.mean(rt ** 2)))
        self.mean_m = dict(zip(mf, self.sc_m.mean_))
        self.mean_t = dict(zip(tf, self.sc_t.mean_))
        self.n_train, self.train_span = len(X), span
        return self

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        mf, tf = list(MARGIN_FEATURES), list(TOTAL_FEATURES)
        Xm, Xt = self.sc_m.transform(X[mf]), self.sc_t.transform(X[tf])
        mu = self.margin.predict(Xm)
        tot = self.total.predict(Xt)
        p_a = norm.cdf(mu / self.sigma_margin)
        p_b = self.logit.predict_proba(Xm)[:, 1]
        p = (p_a + p_b) / 2
        return pd.DataFrame({"exp_margin": mu, "exp_total": tot, "p_margin_model": p_a, "p_logit_model": p_b,
                             "p_home": p}, index=X.index)

    def baseline_margin(self) -> float:
        """Predicted home margin when every matchup feature is 0 (evenly matched, neutral site, no travel)."""
        return float(self.margin.intercept_ - sum(self.margin.coef_[i] * self.sc_m.mean_[i] / self.sc_m.scale_[i]
                                                   for i in range(len(MARGIN_FEATURES))))

    def contributions(self, x: dict) -> list[dict]:
        """Points-of-margin contribution of each feature relative to a neutral matchup
        (all differences 0). Contributions + baseline_margin() = expected margin."""
        out = []
        for i, f in enumerate(MARGIN_FEATURES):
            c = self.margin.coef_[i] * x[f] / self.sc_m.scale_[i]
            out.append({"feature": f, "label": MARGIN_FEATURES[f], "value": x[f], "points": float(c)})
        return sorted(out, key=lambda d: -abs(d["points"]))

    def total_contributions(self, x: dict) -> list[dict]:
        out = []
        for i, f in enumerate(TOTAL_FEATURES):
            c = self.total.coef_[i] * (x[f] - self.sc_t.mean_[i]) / self.sc_t.scale_[i]
            out.append({"feature": f, "label": TOTAL_FEATURES[f], "value": x[f], "points": float(c)})
        return sorted(out, key=lambda d: -abs(d["points"]))

    def coef_table(self) -> list[dict]:
        rows = []
        for i, f in enumerate(MARGIN_FEATURES):
            rows.append({"feature": f, "label": MARGIN_FEATURES[f], "pts_per_sd": float(self.margin.coef_[i]),
                         "logit_per_sd": float(self.logit.coef_[0][i]), "sd": float(self.sc_m.scale_[i])})
        return rows

    def distribution(self, mu: float, tot: float, spread_line=None, total_line=None) -> dict:
        s = self.sigma_margin
        bins = list(range(-35, 36, 5))
        hist = []
        for lo in bins[:-1]:
            hist.append({"lo": lo, "hi": lo + 5, "p": float(norm.cdf((lo + 5 - mu) / s) - norm.cdf((lo - mu) / s))})
        out = {"margin_sd": s, "total_sd": self.sigma_total, "margin_hist": hist,
               "margin_p10_p90": [float(mu - 1.2816 * s), float(mu + 1.2816 * s)],
               "total_p10_p90": [float(tot - 1.2816 * self.sigma_total), float(tot + 1.2816 * self.sigma_total)]}
        if spread_line is not None and not (isinstance(spread_line, float) and math.isnan(spread_line)):
            # nflverse spread_line is home-perspective expected margin (positive = home favoured)
            out["p_home_cover"] = float(1 - norm.cdf((spread_line - mu) / s))
        if total_line is not None and not (isinstance(total_line, float) and math.isnan(total_line)):
            out["p_over"] = float(1 - norm.cdf((total_line - tot) / self.sigma_total))
        return out
