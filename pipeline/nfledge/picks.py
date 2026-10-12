"""Model-pick ledger: every positive-EV game pick and every anytime-TD projection the
pipeline logged before kickoff, graded against results. Nothing is filtered after the fact;
the dashboard applies thresholds on top of the full ledger.

Game picks use the last projection logged before kickoff. Runs from 2026-10-12 onward
store the exact prices evaluated (info.values). Earlier runs logged moneylines only, so
their spread/total prices come from the nflverse consensus line (marked price_source).
"""
from __future__ import annotations

import json
import math

import pandas as pd
from scipy.stats import norm

from . import anchor as AN
from . import db as DB
from . import odds as O
from . import tiers as TR


def _opt(market, selection, side, line, odds, model_p, price_source):
    if odds is None or (isinstance(odds, float) and math.isnan(odds)) or not (odds <= -100 or odds >= 100):
        return None
    return {"market": market, "selection": selection, "side": side, "line": line, "odds": float(odds),
            "model_p": float(model_p), "price_source": price_source}


def _grade(o: dict, home: str, hs, as_) -> str:
    if hs is None or (isinstance(hs, float) and math.isnan(hs)):
        return "pending"
    if o["market"] == "moneyline":
        if hs == as_:
            return "push"
        return "won" if (o["side"] == home) == (hs > as_) else "lost"
    if o["market"] == "spread":
        m = (hs - as_) if o["side"] == home else (as_ - hs)
        v = m + o["line"]
        return "won" if v > 0 else "lost" if v < 0 else "push"
    t = hs + as_
    if t == o["line"]:
        return "push"
    return "won" if (o["side"] == "over") == (t > o["line"]) else "lost"


def game_ledger(con, games: pd.DataFrame, sigma_m: float, sigma_t: float, anchors: dict | None = None) -> list[dict]:
    sched = games.set_index("game_id")
    out = []
    for r in DB.last_pregame_games(con):
        info = json.loads(r.get("info") or "{}")
        H, A = r["home_team"], r["away_team"]
        g = sched.loc[r["game_id"]] if r["game_id"] in sched.index else None
        opts = []
        if info.get("values"):
            for v in info["values"]:
                o = _opt(v["market"], v["selection"], v["side"], v.get("line"), v["odds"], v["model_p"], "logged")
                if o:
                    opts.append(o)
        else:
            ph = r["p_home"]
            opts += [_opt("moneyline", f"{H} ML", H, None, r["home_ml"], ph, "logged"),
                     _opt("moneyline", f"{A} ML", A, None, r["away_ml"], 1 - ph, "logged")]
            sl, tl = r["spread_line"], r["total_line"]
            if sl is not None and g is not None:
                pc = float(1 - norm.cdf((sl - r["exp_margin"]) / sigma_m))
                opts += [_opt("spread", f"{H} {-sl:+g}", H, -sl, g.home_spread_odds, pc, "consensus (reconstructed)"),
                         _opt("spread", f"{A} {sl:+g}", A, sl, g.away_spread_odds, 1 - pc, "consensus (reconstructed)")]
            if tl is not None and g is not None:
                po = float(1 - norm.cdf((tl - r["exp_total"]) / sigma_t))
                opts += [_opt("total", f"Over {tl:g}", "over", tl, g.over_odds, po, "consensus (reconstructed)"),
                         _opt("total", f"Under {tl:g}", "under", tl, g.under_odds, 1 - po, "consensus (reconstructed)")]
            opts = [o for o in opts if o]
        # pair each option with its opposite side to remove the vig
        by_market: dict = {}
        for o in opts:
            by_market.setdefault(o["market"], []).append(o)
        for mk, pair in by_market.items():
            if len(pair) != 2:
                continue
            nv = O.remove_vig_proportional([O.american_to_implied(p["odds"]) for p in pair])
            season = int(r["game_id"][:4])
            coef = (anchors or {}).get(season)        # fit only on seasons before this pick's season
            for o, fair in zip(pair, nv):
                dec = O.american_to_decimal(o["odds"])
                ev = O.expected_profit(o["model_p"], dec)
                pa = AN.anchored(coef, o["market"], o["model_p"], fair)
                ev_a = O.expected_profit(pa, dec)
                if ev <= 0 and ev_a <= 0:
                    continue          # ledger holds sides that were positive-EV on either basis
                res = _grade(o, H, r.get("home_score"), r.get("away_score"))
                out.append({**o, "game_id": r["game_id"], "matchup": f"{A} @ {H}", "kickoff_utc": r["kickoff_utc"],
                            "logged_at": r["run_id"], "season": int(r["game_id"][:4]), "week": int(r["game_id"][5:7]),
                            "no_vig": fair, "edge_pp": (o["model_p"] - fair) * 100, "ev": ev, "result": res,
                            "anchored_p": pa, "anchored_edge_pp": (pa - fair) * 100, "anchored_ev": ev_a,
                            "profit": (dec - 1) if res == "won" else -1.0 if res == "lost" else 0.0,
                            "final": None if res == "pending" else f"{A} {int(r['away_score'])}, {H} {int(r['home_score'])}"})
    return sorted(out, key=lambda d: (d["kickoff_utc"], d["game_id"], d["market"]))


def td_ledger(con, usage_by_game: dict, pbp_games: set) -> list[dict]:
    """All logged anytime-TD projections. Graded from snap-count results when available,
    otherwise from play-by-play (no touches = void, like most books)."""
    out = []
    for r in DB.last_pregame_tds(con):
        p = float(r["p_anytime"])
        if r.get("played") is not None:
            res = "won" if r["scored"] else "lost" if r["played"] else "void"
        elif r["game_id"] in pbp_games:
            u = usage_by_game.get(r["game_id"], {}).get(r["player_id"])
            res = "void" if not u or u["touches"] == 0 else ("won" if u["tds"] > 0 else "lost")
        else:
            res = "pending"
        out.append({"game_id": r["game_id"], "season": int(r["game_id"][:4]), "week": int(r["game_id"][5:7]),
                    "kickoff_utc": r["kickoff_utc"], "logged_at": r["run_id"], "player_id": r["player_id"],
                    "name": r["player_name"], "team": r["team"], "position": r["position"], "p": p,
                    "score": TR.td_score(p), "status": r["status"], "odds": r["market_odds"], "result": res})
    return sorted(out, key=lambda d: (d["kickoff_utc"], -d["p"]))


def rec_ledger(con) -> list[dict]:
    """The Spread / ML / Total recommendation shown before kickoff (last pre-game run), graded."""
    out = []
    for r in DB.last_pregame_games(con):
        info = json.loads(r.get("info") or "{}")
        H, A = r["home_team"], r["away_team"]
        for mk, rc in (info.get("recs") or {}).items():
            o = {"market": mk, "side": rc["side"], "line": rc["line"]}
            res = _grade(o, H, r.get("home_score"), r.get("away_score"))
            dec = O.american_to_decimal(rc["odds"])
            out.append({**rc, "market": mk, "game_id": r["game_id"], "matchup": f"{A} @ {H}", "kickoff_utc": r["kickoff_utc"],
                        "logged_at": r["run_id"], "season": int(r["game_id"][:4]), "week": int(r["game_id"][5:7]), "result": res,
                        "profit": (dec - 1) if res == "won" else -1.0 if res == "lost" else 0.0,
                        "final": None if res == "pending" else f"{A} {int(r['away_score'])}, {H} {int(r['home_score'])}"})
    return sorted(out, key=lambda d: (d["kickoff_utc"], d["game_id"], d["market"]))
