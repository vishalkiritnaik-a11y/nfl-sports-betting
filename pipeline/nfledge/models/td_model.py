"""Anytime-touchdown model: expected opportunities x per-opportunity TD rates,
then a calibration layer.

Pathways (no double counting; each play has exactly one ball carrier/target):
  rushing  : carries inside the 5, 6-10, 11-20, outside the 20
  receiving: end-zone targets, other red-zone targets, other targets
lambda_rush, lambda_rec = sum(expected opportunities * league TD rate per
opportunity) * player finishing multiplier * opponent multiplier.
P(anytime) = calibrated 1 - exp(-(lambda_rush + lambda_rec)).
The Poisson combination treats TD *counts* as Poisson; the calibration layer
(fit on later seasons only) corrects for over-dispersion and correlation.
Return/defensive TDs are not modelled (they settle anytime-TD bets but are rare
for offensive players); passing TDs never count for a QB's anytime TD.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ZONES_RUSH = ["c_i5", "c_6_10", "c_11_20", "c_out"]
ZONES_REC = ["t_ez", "t_rz", "t_out"]
ALL_ZONES = ZONES_RUSH + ZONES_REC
POSITIONS = ["QB", "RB", "WR", "TE"]
DECAY = 0.85
MAX_HIST = 12
K_PLAYER_EFF = 4.0    # expected TDs of shrinkage for finishing multiplier
K_OPP = 8.0           # expected TDs of shrinkage for opponent multiplier


def player_game_usage(pbp: pd.DataFrame) -> pd.DataFrame:
    """Per (game_id, team, player) opportunity counts and TDs from play-by-play."""
    p = pbp[(pbp.season_type.isin(["REG", "POST"])) & (pbp.two_point_attempt != 1) & (pbp.aborted_play != 1)]
    yl = p.yardline_100
    r = p[(p.rush_attempt == 1) & p.rusher_player_id.notna()].copy()
    r["zone"] = np.select([yl[r.index] <= 5, yl[r.index] <= 10, yl[r.index] <= 20], ["c_i5", "c_6_10", "c_11_20"], "c_out")
    r["td"] = (r.rush_touchdown == 1) & (r.td_player_id == r.rusher_player_id)
    t = p[(p.pass_attempt == 1) & (p.sack != 1) & p.receiver_player_id.notna()].copy()
    ez = t.air_yards.fillna(-99) >= yl[t.index]
    t["zone"] = np.select([ez, yl[t.index] <= 20], ["t_ez", "t_rz"], "t_out")
    t["td"] = (t.pass_touchdown == 1) & (t.td_player_id == t.receiver_player_id)
    rc = r.groupby(["game_id", "posteam", "rusher_player_id", "zone"]).size().unstack(fill_value=0)
    rc.index = rc.index.set_names(["game_id", "team", "player_id"])
    tc = t.groupby(["game_id", "posteam", "receiver_player_id", "zone"]).size().unstack(fill_value=0)
    tc.index = tc.index.set_names(["game_id", "team", "player_id"])
    u = rc.join(tc, how="outer").fillna(0)
    for z in ALL_ZONES:
        if z not in u:
            u[z] = 0
    rtd = r.groupby(["game_id", "posteam", "rusher_player_id"]).td.sum()
    rtd.index = rtd.index.set_names(["game_id", "team", "player_id"])
    ttd = t.groupby(["game_id", "posteam", "receiver_player_id"]).td.sum()
    ttd.index = ttd.index.set_names(["game_id", "team", "player_id"])
    u["rush_td"] = rtd.reindex(u.index).fillna(0)
    u["rec_td"] = ttd.reindex(u.index).fillna(0)
    # per-zone TDs for league rates
    for z in ZONES_RUSH:
        s = r[r.zone == z].groupby(["game_id", "posteam", "rusher_player_id"]).td.sum()
        s.index = s.index.set_names(["game_id", "team", "player_id"])
        u[f"td_{z}"] = s.reindex(u.index).fillna(0)
    for z in ZONES_REC:
        s = t[t.zone == z].groupby(["game_id", "posteam", "receiver_player_id"]).td.sum()
        s.index = s.index.set_names(["game_id", "team", "player_id"])
        u[f"td_{z}"] = s.reindex(u.index).fillna(0)
    return u.reset_index()


def team_game_opps(usage: pd.DataFrame) -> pd.DataFrame:
    return usage.groupby(["game_id", "team"])[ALL_ZONES + ["rush_td", "rec_td"]].sum().reset_index()


def league_rates(usage: pd.DataFrame) -> dict:
    out = {}
    for z in ALL_ZONES:
        n = usage[z].sum()
        out[z] = float(usage[f"td_{z}"].sum() / n) if n else 0.0
    return out


# ---------------------------------------------------------- player histories

class History:
    """Leak-free player opportunity shares and finishing efficiency."""

    def __init__(self, usage: pd.DataFrame, team_opps: pd.DataFrame, game_dates: pd.DataFrame,
                 active: pd.DataFrame):
        """``active``: (game_id, team, player_id) rows for players who took an offensive snap."""
        gd = game_dates.set_index("game_id").gameday
        u = active.merge(usage, on=["game_id", "team", "player_id"], how="left").fillna(0)
        u = u.merge(team_opps, on=["game_id", "team"], suffixes=("", "_team"))
        u["gameday"] = u.game_id.map(gd)
        u = u.sort_values("gameday")
        self.u = u
        self.by_player = {k: v for k, v in u.groupby("player_id")}

    def shares(self, player_id: str, before: str, pos: str, rates: dict) -> dict:
        h = self.by_player.get(player_id)
        res = {"games": 0, "recent_active": 0}
        if h is not None:
            h = h[(h.gameday < before)]
            # only last ~15 months
            cutoff = (pd.Timestamp(before) - pd.Timedelta(days=450)).strftime("%Y-%m-%d")
            h = h[h.gameday >= cutoff].tail(MAX_HIST)
        if h is None or h.empty:
            for z in ALL_ZONES:
                res[f"sh_{z}"] = 0.0
            res["eff"] = 1.0
            return res
        w = DECAY ** np.arange(len(h))[::-1]
        res["games"] = int(len(h))
        pn = lambda c: float((h[c] * w).sum())
        tn = lambda c: float((h[f"{c}_team"] * w).sum())
        # hierarchical shrinkage: broad share -> narrower zones
        n_g = float(w.sum())
        carries = sum(pn(z) for z in ZONES_RUSH)
        team_car = sum(tn(z) for z in ZONES_RUSH)
        targets = sum(pn(z) for z in ZONES_REC)
        team_tgt = sum(tn(z) for z in ZONES_REC)
        k_car, k_tgt = 2 * team_car / n_g, 2 * team_tgt / n_g
        car_sh = carries / (team_car + k_car) if team_car else 0.0
        tgt_sh = targets / (team_tgt + k_tgt) if team_tgt else 0.0
        rz_car = (pn("c_i5") + pn("c_6_10") + pn("c_11_20"))
        rz_car_t = (tn("c_i5") + tn("c_6_10") + tn("c_11_20"))
        rz_sh = (rz_car + 8 * car_sh) / (rz_car_t + 8)
        i10 = pn("c_i5") + pn("c_6_10"); i10t = tn("c_i5") + tn("c_6_10")
        i10_sh = (i10 + 6 * rz_sh) / (i10t + 6)
        i5_sh = (pn("c_i5") + 4 * i10_sh) / (tn("c_i5") + 4)
        rzt = pn("t_rz") + pn("t_ez"); rzt_t = tn("t_rz") + tn("t_ez")
        rzt_sh = (rzt + 8 * tgt_sh) / (rzt_t + 8)
        ez_sh = (pn("t_ez") + 6 * rzt_sh) / (tn("t_ez") + 6)
        res.update({"sh_c_i5": i5_sh, "sh_c_6_10": i10_sh, "sh_c_11_20": rz_sh, "sh_c_out": car_sh,
                    "sh_t_ez": ez_sh, "sh_t_rz": rzt_sh, "sh_t_out": tgt_sh})
        # finishing: actual TDs vs expected given opportunities (last 2 seasons, unweighted)
        exp_td = sum(float(h[z].sum()) * rates[z] for z in ALL_ZONES)
        act_td = float(h.rush_td.sum() + h.rec_td.sum())
        res["eff"] = (act_td + K_PLAYER_EFF) / (exp_td + K_PLAYER_EFF)
        res["recent_active"] = int((h.gameday >= (pd.Timestamp(before) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")).sum())
        res["raw"] = {
            "carries_pg": carries / n_g, "targets_pg": targets / n_g,
            "i10_carries_pg": i10 / n_g, "rz_targets_pg": rzt / n_g, "ez_targets_pg": pn("t_ez") / n_g,
            "share_carries": carries / team_car if team_car else 0.0,
            "share_targets": targets / team_tgt if team_tgt else 0.0,
            "share_i10_carries": i10 / i10t if i10t else 0.0,
            "share_rz_targets": rzt / rzt_t if rzt_t else 0.0,
        }
        return res


def renormalize(rows: list[dict], available: set[str]) -> None:
    """Redistribute opportunity shares of unavailable players to available
    teammates proportionally, so team shares stay consistent."""
    for z in ALL_ZONES:
        key = f"sh_{z}"
        tot = sum(r[key] for r in rows)
        avail = sum(r[key] for r in rows if r["player_id"] in available)
        if avail <= 0:
            continue
        target = min(1.0, tot)
        scale = target / avail
        for r in rows:
            r[f"adj_{z}"] = r[key] * scale if r["player_id"] in available else 0.0


# ---------------------------------------------------------- team opportunities

@dataclass
class TeamOppModel:
    """E[team opportunities of zone z] = a_z + b_z * exp_points + c_z * exp_margin, fit by OLS."""
    coefs: dict = field(default_factory=dict)

    def fit(self, df: pd.DataFrame):
        X = np.column_stack([np.ones(len(df)), df.exp_points, df.exp_margin])
        for z in ALL_ZONES:
            beta, *_ = np.linalg.lstsq(X, df[z].values, rcond=None)
            self.coefs[z] = beta.tolist()
        return self

    def predict(self, exp_points: float, exp_margin: float) -> dict:
        return {z: max(0.05, b[0] + b[1] * exp_points + b[2] * exp_margin) for z, b in self.coefs.items()}


@dataclass
class TDModel:
    rates: dict = field(default_factory=dict)
    opp_model: TeamOppModel = None
    calib: LogisticRegression = None
    iso: IsotonicRegression = None
    n_train: int = 0

    @staticmethod
    def lambdas(sh: dict, team_opps: dict, rates: dict, eff: float, opp_rush: float, opp_rec: float,
                prefix: str = "adj_") -> tuple[float, float, dict]:
        exp_opps = {z: sh.get(f"{prefix}{z}", sh.get(f"sh_{z}", 0.0)) * team_opps[z] for z in ALL_ZONES}
        lr = sum(exp_opps[z] * rates[z] for z in ZONES_RUSH) * eff * opp_rush
        lc = sum(exp_opps[z] * rates[z] for z in ZONES_REC) * eff * opp_rec
        return lr, lc, exp_opps

    @staticmethod
    def design(df: pd.DataFrame) -> np.ndarray:
        lam = (df.lam_rush + df.lam_rec).clip(lower=1e-4)
        ll = np.log(lam)
        snap_prev = df["snap_prev"].fillna(0) if "snap_prev" in df else np.zeros(len(df))
        snap_avg3 = df["snap_avg3"].fillna(0) if "snap_avg3" in df else np.zeros(len(df))
        cols = [ll, ll ** 2] + [(df.position == p).astype(float) for p in POSITIONS[:-1]] + [
            df.lam_rush / lam, np.minimum(df.games, 6) / 6.0, (df.games == 0).astype(float), snap_prev, snap_avg3]
        return np.column_stack(cols)

    def fit_calibration(self, df: pd.DataFrame):
        X = self.design(df)
        self.calib = LogisticRegression(C=1.0, max_iter=5000).fit(X, df.y)
        self.n_train = len(df)
        return self

    def prob(self, df: pd.DataFrame) -> np.ndarray:
        return self.calib.predict_proba(self.design(df))[:, 1]

    def calib_coefs(self) -> dict:
        names = ["log_lambda", "log_lambda_sq", "is_QB", "is_RB", "is_WR", "rush_fraction", "history_depth", "no_history",
                 "snap_share_last_game", "snap_share_last3"]
        return dict(zip(names, [float(c) for c in self.calib.coef_[0]])) | {"intercept": float(self.calib.intercept_[0])}


def raw_poisson_p(lr: float, lc: float) -> float:
    return 1 - math.exp(-(lr + lc))


def first_td_approx(lams: list[float], p_any_game_td: float = 0.985) -> list[float]:
    """Approximate first-TD probability: share of the game's total TD intensity.
    Shown only for contrast with anytime-TD; not a separate market model."""
    tot = sum(lams)
    return [p_any_game_td * l / tot if tot else 0.0 for l in lams]


def snap_features(act: pd.DataFrame) -> pd.DataFrame:
    """Leak-free snap-share features per (game_id, player_id): share in the player's previous
    game and mean of his previous three (any team, any season)."""
    a = act.sort_values("gameday")
    g = a.groupby("player_id").offense_pct
    a = a.assign(snap_prev=g.shift(1), snap_avg3=g.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean()))
    return a[["game_id", "player_id", "snap_prev", "snap_avg3"]]


def snap_features_live(act: pd.DataFrame, player_id: str, before: str) -> dict:
    x = act[(act.player_id == player_id) & (act.gameday < before)].sort_values("gameday").offense_pct.tail(3)
    if x.empty:
        return {"snap_prev": 0.0, "snap_avg3": 0.0}
    return {"snap_prev": float(x.iloc[-1]), "snap_avg3": float(x.mean())}
