"""Assemble leak-free player-game rows for the anytime-TD model."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .models import td_model as TD

OFF_POS = {"QB", "RB", "FB", "WR", "TE"}


def active_players(snaps: pd.DataFrame, players: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """(game_id, team, player_id, position) for offensive skill players who took >=1 offensive snap."""
    s = snaps[(snaps.offense_snaps > 0) & snaps.position.isin(OFF_POS)].copy()
    m = players.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id
    s["player_id"] = s.pfr_player_id.map(m)
    s = s.dropna(subset=["player_id"])
    s["position"] = s.position.replace({"FB": "RB"})
    from .teamdata import RENAME
    s["team"] = s.team.replace(RENAME)
    return s[["game_id", "team", "player_id", "position", "player", "offense_pct"]]


class DefenseHistory:
    """Per defense: opportunities faced by zone and TDs allowed (rush/rec), leak-free."""

    def __init__(self, team_opps: pd.DataFrame, games: pd.DataFrame):
        g = games[["game_id", "home_team", "away_team", "gameday"]]
        t = team_opps.merge(g, on="game_id")
        t["defense"] = np.where(t.team == t.home_team, t.away_team, t.home_team)
        self.by_def = {k: v.sort_values("gameday") for k, v in t.groupby("defense")}

    def raw(self, defense: str, before: str) -> dict:
        h = self.by_def.get(defense)
        if h is None:
            return {}
        cutoff = (pd.Timestamp(before) - pd.Timedelta(days=450)).strftime("%Y-%m-%d")
        h = h[(h.gameday < before) & (h.gameday >= cutoff)].tail(12)
        out = {f"d_{z}": float(h[z].sum()) for z in TD.ALL_ZONES}
        out["d_rush_td"] = float(h.rush_td.sum())
        out["d_rec_td"] = float(h.rec_td.sum())
        out["d_games"] = int(len(h))
        return out


def opp_multipliers(row: dict, rates: dict) -> tuple[float, float]:
    er = sum(row.get(f"d_{z}", 0) * rates[z] for z in TD.ZONES_RUSH)
    ec = sum(row.get(f"d_{z}", 0) * rates[z] for z in TD.ZONES_REC)
    mr = (row.get("d_rush_td", 0) + TD.K_OPP) / (er + TD.K_OPP)
    mc = (row.get("d_rec_td", 0) + TD.K_OPP) / (ec + TD.K_OPP)
    return mr, mc


def hist_counts(hist: TD.History, player_id: str, before: str) -> dict:
    h = hist.by_player.get(player_id)
    out = {f"h_{z}": 0.0 for z in TD.ALL_ZONES}
    out["h_td"] = 0.0
    if h is None:
        return out
    cutoff = (pd.Timestamp(before) - pd.Timedelta(days=450)).strftime("%Y-%m-%d")
    h = h[(h.gameday < before) & (h.gameday >= cutoff)].tail(TD.MAX_HIST)
    for z in TD.ALL_ZONES:
        out[f"h_{z}"] = float(h[z].sum())
    out["h_td"] = float(h.rush_td.sum() + h.rec_td.sum())
    return out


def eff_from(row: dict, rates: dict) -> float:
    exp_td = sum(row[f"h_{z}"] * rates[z] for z in TD.ALL_ZONES)
    return (row["h_td"] + TD.K_PLAYER_EFF) / (exp_td + TD.K_PLAYER_EFF)


def build_rows(games_sel: pd.DataFrame, game_preds: pd.DataFrame, active: pd.DataFrame, usage: pd.DataFrame,
               hist: TD.History, dhist: DefenseHistory, team_opps: pd.DataFrame, rates_for_shares: dict) -> pd.DataFrame:
    """Historical rows: one per active skill player per played game."""
    gp = game_preds.set_index("game_id")
    act = active.merge(usage[["game_id", "team", "player_id", "rush_td", "rec_td"]], on=["game_id", "team", "player_id"], how="left").fillna({"rush_td": 0, "rec_td": 0})
    act_by_tg = {k: v for k, v in act.groupby(["game_id", "team"])}
    to = team_opps.set_index(["game_id", "team"])
    rows = []
    for g in games_sel.itertuples(index=False):
        if g.game_id not in gp.index:
            continue
        pr = gp.loc[g.game_id]
        for side, team, opp in (("home", g.home_team, g.away_team), ("away", g.away_team, g.home_team)):
            tg = act_by_tg.get((g.game_id, team))
            if tg is None:
                continue
            sign = 1 if side == "home" else -1
            exp_margin = sign * pr.exp_margin
            exp_points = (pr.exp_total + exp_margin) / 2
            d = dhist.raw(opp, g.gameday)
            prow = []
            for p in tg.itertuples(index=False):
                sh = hist.shares(p.player_id, g.gameday, p.position, rates_for_shares)
                r = {"game_id": g.game_id, "season": g.season, "week": g.week, "team": team, "opp": opp,
                     "player_id": p.player_id, "position": p.position, "exp_points": exp_points,
                     "exp_margin": exp_margin, "games": sh["games"],
                     **{k: v for k, v in sh.items() if k.startswith("sh_")},
                     **hist_counts(hist, p.player_id, g.gameday), **d,
                     "y": int((p.rush_td + p.rec_td) > 0), "tds": p.rush_td + p.rec_td}
                prow.append(r)
            TD.renormalize(prow, {r["player_id"] for r in prow})
            if (g.game_id, team) in to.index:
                actual = to.loc[(g.game_id, team)]
                for r in prow:
                    for z in TD.ALL_ZONES:
                        r[f"team_{z}"] = float(actual[z])
            rows.extend(prow)
    return pd.DataFrame(rows)


def apply_lambdas(df: pd.DataFrame, rates: dict, opp_model: TD.TeamOppModel) -> pd.DataFrame:
    df = df.copy()
    lr, lc = [], []
    for r in df.to_dict("records"):
        team_opps = opp_model.predict(r["exp_points"], r["exp_margin"])
        mr, mc = opp_multipliers(r, rates)
        a, b, _ = TD.TDModel.lambdas(r, team_opps, rates, eff_from(r, rates), mr, mc)
        lr.append(a); lc.append(b)
    df["lam_rush"], df["lam_rec"] = lr, lc
    return df
