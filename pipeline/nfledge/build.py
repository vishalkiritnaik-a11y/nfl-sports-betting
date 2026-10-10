"""End-to-end pipeline: ingest -> features -> models -> JSON for the dashboard
+ append-only prediction log.  Run:  python -m nfledge.build
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import pickle
import re
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config as C
from . import db as DB
from . import features as F
from . import matchups as M
from . import odds as O
from . import stadiums, tddata as D, teamdata as T
from .ingest import nflverse as N, odds_api, weather as W
from .models import td_model as TD
from .models.game_model import MARGIN_FEATURES, TOTAL_FEATURES, GameModel, game_features

log = logging.getLogger("nfledge")
NOW = datetime.now(timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"
UNCERTAIN = {"Questionable", "Doubtful"}
KEY_POS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL", "OL": "OL",
           "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "OLB": "EDGE/LB", "LB": "EDGE/LB", "ILB": "EDGE/LB",
           "MLB": "EDGE/LB", "CB": "CB", "S": "S", "FS": "S", "SS": "S", "DB": "CB", "K": "K", "P": "P"}


def _f(x, nd=4):
    if x is None:
        return None
    try:
        if isinstance(x, (float, np.floating)) and (math.isnan(x) or math.isinf(x)):
            return None
    except TypeError:
        pass
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return round(float(x), nd)
    return x


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (float, np.floating, np.integer)):
        return _f(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), separators=(",", ":"), allow_nan=False))


# ------------------------------------------------------------------ helpers

def record_entering(games: pd.DataFrame, team: str, season: int, before: str) -> str:
    g = games[(games.season == season) & (games.gameday < before) & games.home_score.notna() & (games.game_type == "REG")
              & ((games.home_team == team) | (games.away_team == team))]
    w = l = t = 0
    for r in g.itertuples(index=False):
        m = (r.home_score - r.away_score) * (1 if r.home_team == team else -1)
        w, l, t = w + (m > 0), l + (m < 0), t + (m == 0)
    return f"{w}-{l}" + (f"-{t}" if t else "")


def head_to_head(games: pd.DataFrame, a: str, b: str, before: str, cur_qbs: dict, cur_coaches: dict, n=6) -> list:
    g = games[(((games.home_team == a) & (games.away_team == b)) | ((games.home_team == b) & (games.away_team == a)))
              & (games.gameday < before) & games.home_score.notna()].sort_values("gameday").tail(n)
    out = []
    for r in g.iloc[::-1].itertuples(index=False):
        same_qbs = sum(1 for side in ("home", "away") if cur_qbs.get(getattr(r, f"{side}_team")) == getattr(r, f"{side}_qb_name"))
        same_coaches = sum(1 for side in ("home", "away") if cur_coaches.get(getattr(r, f"{side}_team")) == getattr(r, f"{side}_coach"))
        out.append({"game_id": r.game_id, "season": r.season, "week": r.week, "gameday": r.gameday,
                    "home": r.home_team, "away": r.away_team, "home_score": r.home_score, "away_score": r.away_score,
                    "total": r.home_score + r.away_score, "home_qb": r.home_qb_name, "away_qb": r.away_qb_name,
                    "home_coach": r.home_coach, "away_coach": r.away_coach,
                    "same_qbs": same_qbs, "same_coaches": same_coaches,
                    "relevance": "high" if same_qbs == 2 and same_coaches == 2 else "partial" if same_qbs + same_coaches >= 2 else "low"})
    return out


def market_from_schedule(g) -> dict | None:
    if pd.isna(g.home_moneyline) and pd.isna(g.spread_line):
        return None
    m = {"source": "nflverse consensus line", "book": "consensus", "snapshot": None}
    for k in ("home_moneyline", "away_moneyline", "spread_line", "home_spread_odds", "away_spread_odds",
              "total_line", "over_odds", "under_odds"):
        v = getattr(g, k)
        m[k] = None if pd.isna(v) else float(v)
    return m


def market_from_api(ev: dict) -> dict | None:
    """Best available price per side across books, plus the book offering it."""
    if not ev or not ev.get("books"):
        return None
    best = {}
    for book, b in ev["books"].items():
        for side in ("home", "away"):
            k = f"ml_{side}"
            if k in b and (k not in best or O.american_to_decimal(b[k]) > O.american_to_decimal(best[k][0])):
                best[k] = (b[k], book)
    if "ml_home" not in best:
        return None
    first = next(iter(ev["books"].values()))
    sp = first.get("spread_home")
    return {"source": "The Odds API", "snapshot": ev["snapshot"],
            "home_moneyline": best["ml_home"][0], "home_ml_book": best["ml_home"][1],
            "away_moneyline": best["ml_away"][0], "away_ml_book": best["ml_away"][1],
            # nflverse convention: spread_line = expected home margin (home favoured -> positive)
            "spread_line": -sp if sp is not None else None,
            "home_spread_odds": first.get("spread_home_price"), "away_spread_odds": first.get("spread_away_price"),
            "total_line": first.get("total_over"), "over_odds": first.get("total_over_price"),
            "under_odds": first.get("total_under_price"), "book": "best of " + ", ".join(ev["books"].keys())}


def value_rows(pred: dict, dist: dict, mkt: dict | None, home: str, away: str) -> list[dict]:
    if not mkt:
        return []
    rows = []
    hm, am = mkt.get("home_moneyline"), mkt.get("away_moneyline")
    if hm and am:
        for team, p, a, b in ((home, pred["p_home"], hm, am), (away, 1 - pred["p_home"], am, hm)):
            ev = O.evaluate_two_way(p, a, b)
            rows.append({"market": "moneyline", "selection": f"{team} ML", "team": team, "model_p": p, **ev})
    sl = mkt.get("spread_line")
    if sl is not None and "p_home_cover" in dist and mkt.get("home_spread_odds") and mkt.get("away_spread_odds"):
        ph = dist["p_home_cover"]
        home_line = -sl
        for team, p, line, a, b in ((home, ph, home_line, mkt["home_spread_odds"], mkt["away_spread_odds"]),
                                    (away, 1 - ph, -home_line, mkt["away_spread_odds"], mkt["home_spread_odds"])):
            ev = O.evaluate_two_way(p, a, b)
            rows.append({"market": "spread", "selection": f"{team} {line:+g}", "team": team, "model_p": p, **ev})
    tl = mkt.get("total_line")
    if tl is not None and "p_over" in dist and mkt.get("over_odds") and mkt.get("under_odds"):
        po = dist["p_over"]
        for sel, p, a, b in ((f"Over {tl:g}", po, mkt["over_odds"], mkt["under_odds"]),
                             (f"Under {tl:g}", 1 - po, mkt["under_odds"], mkt["over_odds"])):
            ev = O.evaluate_two_way(p, a, b)
            rows.append({"market": "total", "selection": sel, "team": None, "model_p": p, **ev})
    return rows


def game_confidence(pred, fe_meta, inj_flags, weather, played_counts) -> dict:
    score, reasons = 0, []
    dis = abs(pred["p_margin_model"] - pred["p_logit_model"])
    if dis < 0.03:
        score += 1; reasons.append("Margin and logistic models agree (within 3 pts)")
    elif dis > 0.07:
        score -= 1; reasons.append(f"Models disagree by {dis*100:.0f} pts")
    if min(played_counts) < 3:
        score -= 1; reasons.append("Fewer than 3 games of current-season data for a team (prior season weighted heavily)")
    else:
        score += 1; reasons.append("At least 3 current-season games for both teams")
    if inj_flags.get("qb_uncertain"):
        score -= 2; reasons.append("Starting QB availability uncertain")
    if inj_flags.get("n_key_uncertain", 0) >= 3:
        score -= 1; reasons.append(f"{inj_flags['n_key_uncertain']} starters/rotation players questionable, doubtful or not practising")
    if weather and weather.get("status") == "forecast":
        wr = weather.get("wind_range_mph")
        if (weather.get("wind_mph") or 0) >= 15 or (wr and wr[1] - wr[0] > 10):
            score -= 1; reasons.append("Wind forecast is high or uncertain")
    if abs(pred["p_home"] - 0.5) < 0.05:
        reasons.append("Near coin-flip: small information changes can flip the pick")
    label = "High" if score >= 2 else "Medium" if score >= 0 else "Low"
    return {"label": label, "score": score, "reasons": reasons}


def explain_game(contribs: list, home: str, away: str) -> tuple[list, list]:
    """Top supporting factors for each side, in points of margin."""
    fav_home = [c for c in contribs if c["points"] > 0.25][:4]
    fav_away = [c for c in contribs if c["points"] < -0.25][:4]
    return ([f"{c['label']}: +{c['points']:.1f} pts toward {home}" for c in fav_home],
            [f"{c['label']}: +{-c['points']:.1f} pts toward {away}" for c in fav_away])


# ------------------------------------------------------------------ main

def run(args):
    t0 = time.time()
    run_id = NOW.strftime(ISO)
    games, pbp, season = T.load()
    games["kickoff_utc"] = [W.kickoff_utc(d, t).strftime(ISO) for d, t in zip(games.gameday, games.gametime)]
    unplayed = games[(games.season == season) & games.home_score.isna()]
    upcoming = unplayed[unplayed.kickoff_utc > (NOW - pd.Timedelta(hours=5)).strftime(ISO)]
    if len(upcoming):
        cur_week = int(upcoming.week.min())
    else:
        cur_week = int(games[games.season == season].week.max())
    log.info("season %s current week %s (%.0fs)", season, cur_week, time.time() - t0)

    # ---------------- team features & models
    gf, metas, tgs, rater, qbr, elo_df, elo_now, venue_cache = T.build_game_frame(games, pbp, 2017)
    played = gf[gf.played]
    bt_parts = []
    for S in range(C.BACKTEST_FIRST_SEASON, season + 1):
        tr, te = played[played.season < S], gf[(gf.season == S)]
        m = GameModel().fit(tr, tr.margin.values, tr.total.values, f"2017-{S-1}")
        bt_parts.append(te[["game_id"]].join(m.predict(te)))
    gp_bt = pd.concat(bt_parts)  # walk-forward, season-level retrain
    live = GameModel().fit(played, played.margin.values, played.total.values,
                           f"2017-{season} wk{cur_week-1}" if cur_week > 1 else f"2017-{season-1}")
    gp_live = gf[~gf.played][["game_id"]].join(live.predict(gf[~gf.played]))
    log.info("game models done (%.0fs)", time.time() - t0)

    # ---------------- TD data
    usage = TD.player_game_usage(pbp)
    usage["season"] = usage.game_id.str[:4].astype(int)
    tog = TD.team_game_opps(usage)
    players = N.players()
    pos_map = players.set_index("gsis_id").position.replace({"FB": "RB"}).to_dict()
    name_map = players.set_index("gsis_id").display_name.to_dict()
    head_map = players.set_index("gsis_id").headshot.to_dict()
    snaps = pd.concat([x for x in (N.snap_counts(s, s == season) for s in range(C.PLAYER_FIRST_SEASON, season + 1)) if x is not None])
    snaps["team"] = snaps.team.replace(T.RENAME)
    act = D.active_players(snaps, players, games)
    hist = TD.History(usage, tog, games[["game_id", "gameday"]], act)
    dhist = D.DefenseHistory(tog, games)
    pred_all = pd.concat([gp_bt, gp_live]).drop_duplicates("game_id", keep="first")
    # TD rows cache (historic rows never change once built)
    cache_f = C.CACHE_DIR / f"tdrows_{C.MODEL_VERSION}.pkl"
    rows = pd.read_pickle(cache_f) if cache_f.exists() and not args.rebuild else pd.DataFrame()
    done = set(rows.game_id) if len(rows) else set()
    rates0 = TD.league_rates(usage[usage.season < C.BACKTEST_FIRST_SEASON])
    sel = games[(games.season >= C.BACKTEST_FIRST_SEASON) & games.home_score.notna() & ~games.game_id.isin(done)]
    if len(sel):
        new = D.build_rows(sel, gp_bt, act, usage, hist, dhist, tog, rates0)
        rows = pd.concat([rows, new], ignore_index=True)
        rows.to_pickle(cache_f)
    log.info("td rows %d (%.0fs)", len(rows), time.time() - t0)
    gmeta = games.set_index("game_id")
    tg = tog.merge(pred_all, on="game_id")
    tg["home_team"] = tg.game_id.map(gmeta.home_team)
    sign = np.where(tg.team == tg.home_team, 1, -1)
    tg["exp_margin"] = sign * tg.exp_margin
    tg["exp_points"] = (tg.exp_total + tg.exp_margin) / 2
    tg["season"] = tg.game_id.str[:4].astype(int)
    td_bt = []
    for S in range(C.BACKTEST_FIRST_SEASON + 1, season + 1):
        rates = TD.league_rates(usage[usage.season < S])
        om = TD.TeamOppModel().fit(tg[tg.season < S])
        tr = D.apply_lambdas(rows[rows.season < S], rates, om)
        te = D.apply_lambdas(rows[rows.season == S], rates, om)
        if te.empty:
            continue
        # calibration layer trained on earlier seasons' walk-forward lambdas only
        prev = pd.concat([x for x in td_bt]) if td_bt else tr
        cm = TD.TDModel(rates=rates, opp_model=om).fit_calibration(prev if len(prev) > 3000 else tr)
        te["p"] = cm.prob(te)
        td_bt.append(te)
    td_bt = pd.concat(td_bt, ignore_index=True)
    rates_live = TD.league_rates(usage)
    om_live = TD.TeamOppModel().fit(tg[tg.game_id.isin(games[games.home_score.notna()].game_id)])
    td_live = TD.TDModel(rates=rates_live, opp_model=om_live).fit_calibration(td_bt)
    log.info("td models done (%.0fs)", time.time() - t0)

    # ---------------- current-season context
    inj = N.injuries(season, True)
    if inj is not None:
        inj["team"] = inj.team.replace(T.RENAME)
    roster = N.weekly_roster(season, True)
    depth = N.depth_charts(season)
    ftn = N.ftn(season, True)
    stats_cur = N.player_week(season, True)
    teams_df = N.teams()
    teams_df = teams_df[teams_df.team_abbr.isin(set(games[games.season == season].home_team))]
    team_info = {r.team_abbr: {"abbr": r.team_abbr, "name": r.team_name, "nick": r.team_nick, "conf": r.team_conf,
                               "division": r.team_division, "color": r.team_color, "color2": r.team_color2,
                               "logo": r.team_logo_espn} for r in teams_df.itertuples()}
    odds_live = odds_api.game_odds() if odds_api.enabled() else {}
    odds_source = "the-odds-api" if odds_live and "_error" not in odds_live else "nflverse-consensus"

    pbp_cur = pbp[pbp.season == season]
    scheme = M.scheme_tables(pbp_cur, ftn, pos_map, "9999", games) if len(pbp_cur) else {}

    # QB depth (for scenarios)
    qb_depth = {}
    if depth is not None:
        d = depth[depth.pos_abb == "QB"].copy()
        d["team"] = d.team.replace(T.RENAME)
        d = d[d.dt == d.groupby("team").dt.transform("max")].sort_values("pos_rank")
        for team, x in d.groupby("team"):
            qb_depth[team] = x[["gsis_id", "player_name", "pos_rank"]].to_dict("records")

    db = DB.connect()
    DB.log_run(db, run_id, C.MODEL_VERSION, season, cur_week, {k: v.get("source_updated") for k, v in N.FRESHNESS.items()},
               odds_source, "open-meteo")

    gfi = gf.set_index("game_id")
    elo_i = elo_df.set_index("game_id")
    gp_bt_i = gp_bt.set_index("game_id")

    # ----------------------------------------------- per-game record builder
    def injuries_for(team, week):
        if inj is None:
            return []
        x = inj[(inj.team == team) & (inj.week == week)]
        out = []
        for r in x.itertuples(index=False):
            status = r.report_status if isinstance(r.report_status, str) else None
            prac = r.practice_status if isinstance(r.practice_status, str) else None
            out.append({"player_id": r.gsis_id, "name": r.full_name, "position": r.position,
                        "group": KEY_POS.get(r.position, "Other"),
                        "status": status or "No game status yet", "designated": bool(status),
                        "practice": (prac or "").replace(" Participation in Practice", "").replace("Did Not Participate In Practice", "DNP"),
                        "injury": r.report_primary_injury if isinstance(r.report_primary_injury, str) else r.practice_primary_injury if isinstance(r.practice_primary_injury, str) else None})
        order = {"Out": 0, "Doubtful": 1, "Questionable": 2}
        return sorted(out, key=lambda d: (order.get(d["status"], 3), d["group"]))

    def weather_for(g, venue):
        roof_t = venue.get("roof_type") if venue else None
        if not pd.isna(g.home_score):  # played: observed per nflverse
            return {"status": "observed", "roof": g.roof, "temp_f": _f(g.temp), "wind_mph": _f(g.wind),
                    "source": "nflverse game record"}
        if roof_t == "dome":
            return {"status": "indoor", "roof": "dome"}
        if not venue or args.no_weather:
            return {"status": "unavailable", "roof_type": roof_t}
        wx = W.forecast(venue["lat"], venue["lon"], datetime.strptime(g.kickoff_utc, ISO).replace(tzinfo=timezone.utc), NOW)
        if wx is None:
            return {"status": "unavailable", "roof_type": roof_t}
        wx["roof_type"] = roof_t
        if roof_t == "retractable":
            wx["roof_note"] = "Retractable roof: open/closed is decided on game day and is not confirmed here."
        return wx

    def game_record(g, pred: dict, full: bool, week_inj: int | None):
        gid = g.game_id
        x = gfi.loc[gid]
        meta = metas[gid]
        venue = stadiums.info(g.stadium_id, g.stadium)
        home, away = g.home_team, g.away_team
        mdl = live if not pred.get("backtest") else pred["model"]
        xd = x[list(dict.fromkeys(list(MARGIN_FEATURES) + list(TOTAL_FEATURES)))].to_dict()
        contribs = mdl.contributions(xd)
        tcontribs = mdl.total_contributions(xd)
        mkt = None
        if (away, home) in odds_live and not pred.get("backtest"):
            mkt = market_from_api(odds_live[(away, home)])
        if mkt is None:
            mkt = market_from_schedule(g)
            if mkt:
                mkt["snapshot"] = N.FRESHNESS.get("games.csv", {}).get("source_updated")
                if pred.get("backtest"):
                    mkt["source"] = "nflverse closing consensus line"
        dist = mdl.distribution(pred["exp_margin"], pred["exp_total"], mkt.get("spread_line") if mkt else None,
                                mkt.get("total_line") if mkt else None)
        p_home = float(pred["p_home"])
        if mkt and mkt.get("home_moneyline") and mkt.get("away_moneyline"):
            raw = [O.american_to_implied(mkt["home_moneyline"]), O.american_to_implied(mkt["away_moneyline"])]
            nv = O.remove_vig_proportional(raw)
            mkt.update({"home_raw_implied": raw[0], "away_raw_implied": raw[1], "home_no_vig": nv[0],
                        "away_no_vig": nv[1], "overround": O.overround(raw)})
        rec = {
            "game_id": gid, "season": int(g.season), "week": int(g.week), "game_type": g.game_type,
            "gameday": g.gameday, "weekday": g.weekday, "gametime_et": g.gametime, "kickoff_utc": g.kickoff_utc,
            "location": g.location, "div_game": bool(g.div_game == 1),
            "venue": {"stadium": g.stadium, "surface": g.surface if isinstance(g.surface, str) else None,
                      "roof": g.roof if isinstance(g.roof, str) else None, **(venue or {})},
            "lookahead": not full and not pred.get("backtest"),
        }
        played = not pd.isna(g.home_score)
        for side, team in (("home", home), ("away", away)):
            qb = meta["qb"][side]
            rec[side] = {
                "team": team, "record": record_entering(games, team, g.season, g.gameday),
                "elo": float(elo_i.loc[gid, f"{side}_elo"]),
                "qb": {"id": qb["id"], "name": name_map.get(qb["id"], g[f"{side}_qb_name"]), "epa_db": qb["epa_db"],
                       "dropbacks": qb["dropbacks"], "changed": bool(qb["changed"])},
                "rest_days": meta["ctx"][f"{side}_rest"], "travel_km": meta["ctx"][f"{side}_travel_km"],
                "tz_shift": meta["ctx"][f"{side}_tz_shift"],
            }
        rec["prediction"] = {
            "p_home": p_home, "p_away": 1 - p_home, "p_margin_model": pred["p_margin_model"],
            "p_logit_model": pred["p_logit_model"], "elo_prob": float(x.elo_prob),
            "exp_margin": pred["exp_margin"], "exp_total": pred["exp_total"],
            "home_pts": (pred["exp_total"] + pred["exp_margin"]) / 2, "away_pts": (pred["exp_total"] - pred["exp_margin"]) / 2,
            "distribution": dist, "contributions": contribs, "total_contributions": tcontribs,
            "baseline_margin": mdl.baseline_margin(), "baseline_total": float(mdl.total.intercept_),
            "tie_note": C.TIE_RATE_NOTE, "model_version": C.MODEL_VERSION,
            "trained_on": mdl.train_span, "backtest": bool(pred.get("backtest")),
        }
        rec["market"] = mkt
        rec["values"] = value_rows(rec["prediction"], dist, mkt, home, away)
        if played:
            rec["result"] = {"home_score": int(g.home_score), "away_score": int(g.away_score),
                             "winner": home if g.home_score > g.away_score else away if g.away_score > g.home_score else "TIE",
                             "model_correct": None if g.home_score == g.away_score else bool((p_home > 0.5) == (g.home_score > g.away_score))}
        if not full:
            rec["confidence"] = {"label": "Low" if rec["lookahead"] else "n/a",
                                 "reasons": ["Look-ahead projection: injuries, weather and lines will change"] if rec["lookahead"] else []}
            fh, fa = explain_game(contribs, home, away)
            rec["factors"] = {"home": fh, "away": fa}
            return rec
        # ---- full detail
        H, A = meta["home_ratings"], meta["away_ratings"]
        rec["home"]["season"] = rater.season_raw(home, g.season, g.gameday)
        rec["away"]["season"] = rater.season_raw(away, g.season, g.gameday)
        rec["home"]["blended"] = H
        rec["away"]["blended"] = A
        rec["home"]["form"] = F.recent_form(tgs, home, g.gameday)
        rec["away"]["form"] = F.recent_form(tgs, away, g.gameday)
        ih, ia = injuries_for(home, week_inj or g.week), injuries_for(away, week_inj or g.week)
        rec["home"]["injuries"], rec["away"]["injuries"] = ih, ia
        rec["weather"] = weather_for(g, venue)
        # QB scenarios
        scen = []
        flags = {"qb_uncertain": False, "n_key_uncertain": 0}
        for side, il in (("home", ih), ("away", ia)):
            team = g[f"{side}_team"]
            qid = meta["qb"][side]["id"]
            flags["n_key_uncertain"] += sum(1 for r in il if r["group"] not in ("Other", "K", "P") and (r["status"] in UNCERTAIN or (not r["designated"] and r["practice"] == "DNP")))
            st = next((r["status"] for r in il if r["player_id"] == qid), None)
            prac = next((r["practice"] for r in il if r["player_id"] == qid), None)
            if (st in UNCERTAIN or prac == "DNP") and not played:
                flags["qb_uncertain"] = True
            if not played:
                backups = [q for q in qb_depth.get(team, []) if q["gsis_id"] != qid]
                if backups:
                    b = backups[0]
                    alt = game_features(g, games, rater, qbr, {"elo_diff_nohfa": x.elo_pts * 25}, venue_cache, {side: b["gsis_id"]})
                    xa = pd.DataFrame([alt["x"]])
                    pa = live.predict(xa).iloc[0]
                    scen.append({"name": f"{rec[side]['qb']['name']} inactive -> {b['player_name']} starts",
                                 "kind": "qb", "team": team, "trigger_status": st or prac,
                                 "p_home": float(pa.p_home), "exp_margin": float(pa.exp_margin), "exp_total": float(pa.exp_total),
                                 "delta_p_team": float((pa.p_home - p_home) * (1 if side == "home" else -1))})
        if rec["weather"].get("status") == "forecast" and venue and venue.get("roof_type") == "outdoor":
            xw = dict(xd); xw["wind_excess"] = xw["wind_excess"] + 10
            xw2 = pd.DataFrame([xw]); pw = live.predict(xw2).iloc[0]
            scen.append({"name": "Wind 10 mph stronger than forecast", "kind": "weather", "p_home": float(pw.p_home),
                         "exp_margin": float(pw.exp_margin), "exp_total": float(pw.exp_total),
                         "delta_total": float(pw.exp_total - pred["exp_total"])})
        if (rec["weather"].get("status") == "forecast" and rec["weather"].get("wind_mph") is not None
                and venue and venue.get("roof_type") == "outdoor"):
            # apply forecast wind/temp to the total model (observed values are used historically)
            xf = dict(xd)
            xf["wind_excess"] = max(0.0, rec["weather"]["wind_mph"] - 10)
            xf["cold_excess"] = max(0.0, 40 - (rec["weather"].get("temp_f") or 60))
            xf["outdoor"] = 1
            pf = live.predict(pd.DataFrame([xf])).iloc[0]
            rec["prediction"]["exp_total_weather_adj"] = float(pf.exp_total)
            rec["prediction"]["weather_total_delta"] = float(pf.exp_total - pred["exp_total"])
        rec["scenarios"] = scen
        rec["confidence"] = game_confidence(rec["prediction"], meta, flags, rec["weather"], [H["n_games"], A["n_games"]]) \
            if not played or pred.get("backtest") else {"label": "n/a", "reasons": []}
        fh, fa = explain_game(contribs, home, away)
        risks = []
        if flags["qb_uncertain"]:
            risks.append("Starting QB status is uncertain; see scenario projection")
        if min(H["n_games"], A["n_games"]) < 4:
            risks.append("Early-season sample: ratings lean on last season and may be stale after roster changes")
        if mkt and mkt.get("home_no_vig") is not None and abs(p_home - mkt["home_no_vig"]) > 0.08:
            risks.append(f"Model differs from market by {abs(p_home - mkt['home_no_vig'])*100:.0f} pts; the market may know something the model does not (injuries, lineup news)")
        if abs(pred["p_margin_model"] - pred["p_logit_model"]) > 0.05:
            risks.append("Component models disagree")
        if rec["weather"].get("status") == "forecast" and (rec["weather"].get("wind_mph") or 0) >= 15:
            risks.append("High wind forecast: totals and kicking are sensitive to the final forecast")
        risks.append(f"Game outcome noise: 1 SD of margin is about {dist['margin_sd']:.0f} points")
        rec["factors"] = {"home": fh, "away": fa, "risks": risks}
        cur_qbs = {home: rec["home"]["qb"]["name"], away: rec["away"]["qb"]["name"]}
        cur_coaches = {home: g.home_coach, away: g.away_coach}
        rec["h2h"] = head_to_head(games, home, away, g.gameday, cur_qbs, cur_coaches)
        if scheme and g.season == season:
            r1, e1 = M.matchup_rows(scheme, home, away)
            r2, e2 = M.matchup_rows(scheme, away, home)
            rec["matchups"] = {"home_off": r1, "away_off": r2, "home_extras": e1, "away_extras": e2,
                               "unavailable": ["Man vs zone coverage", "Single-high vs two-high shells",
                                               "Route participation", "Personnel groupings"],
                               "note": "Measured from current-season play-by-play and FTN charting. 'edge_z' adds the offense's and the opposing defense's standardised scores; |z| > 1 is flagged."}
        rec["history"] = DB.history_for_game(db, gid)
        return rec

    # ------------------------------------------------- TD rows for live games
    def season_player_lines(team_week_games: set[str]):
        out = {}
        if stats_cur is None:
            return out
        s = stats_cur[(stats_cur.season_type == "REG") | (stats_cur.season_type == "POST")]
        for pid, x in s.groupby("player_id"):
            x = x.sort_values("week")
            out[pid] = {"games": int(len(x)), "carries_pg": float(x.carries.mean()), "targets_pg": float(x.targets.mean()),
                        "receptions_pg": float(x.receptions.mean()), "rush_yds_pg": float(x.rushing_yards.mean()),
                        "rec_yds_pg": float(x.receiving_yards.mean()),
                        "season_tds": int(x.rushing_tds.sum() + x.receiving_tds.sum()),
                        "target_share": _f(x.target_share.mean())}
        return out

    plines = season_player_lines(set())
    snap_recent = {}
    if len(snaps):
        sc = act[act.game_id.str.startswith(str(season))].copy()
        sc["gameday"] = sc.game_id.map(gmeta.gameday)
        for pid, x in sc.sort_values("gameday").groupby("player_id"):
            snap_recent[pid] = [float(v) for v in x.offense_pct.tail(3)]
    ph_games = usage.merge(games[["game_id", "gameday"]], on="game_id")

    def td_recent(pid, before, season_):
        x = ph_games[(ph_games.player_id == pid) & (ph_games.gameday < before)].sort_values("gameday")
        a = act[act.player_id == pid]
        played_ids = set(a.game_id)
        x = x[x.game_id.isin(played_ids)] if played_ids else x
        tds = (x.rush_td + x.rec_td)
        cur = x[x.season == season_]
        return {"last3": int(tds.tail(3).sum()), "last5": int(tds.tail(5).sum()), "last10": int(tds.tail(10).sum()),
                "season_i5_carries": int(cur.c_i5.sum()), "season_i10_carries": int((cur.c_i5 + cur.c_6_10).sum()),
                "season_rz_targets": int((cur.t_rz + cur.t_ez).sum()), "season_ez_targets": int(cur.t_ez.sum()),
                "season_tds": int((cur.rush_td + cur.rec_td).sum())}

    def def_vs_pos(season_):
        u = usage[usage.season == season_].merge(act[["game_id", "player_id", "position"]], on=["game_id", "player_id"], how="left")
        u["position"] = u.position.fillna(u.player_id.map(pos_map))
        u["defense"] = np.where(u.team == u.game_id.map(gmeta.home_team), u.game_id.map(gmeta.away_team), u.game_id.map(gmeta.home_team))
        ng = u.groupby("defense").game_id.nunique()
        t = u.groupby(["defense", "position"])[["rush_td", "rec_td"]].sum().sum(axis=1).unstack(fill_value=0)
        t = t.div(ng, axis=0)
        out = {}
        for pos in ("QB", "RB", "WR", "TE"):
            if pos not in t:
                continue
            col = t[pos]
            rk = col.rank(ascending=False, method="min")
            for d_, v in col.items():
                out.setdefault(d_, {})[pos] = {"td_pg": float(v), "rank": int(rk[d_]), "games": int(ng[d_])}
        return out

    dvp = def_vs_pos(season)

    def td_live_rows(g, pred, inj_home, inj_away):
        out = []
        for side, team, opp, il in (("home", g.home_team, g.away_team, inj_home), ("away", g.away_team, g.home_team, inj_away)):
            sign = 1 if side == "home" else -1
            em = sign * pred["exp_margin"]
            ep = (pred["exp_total"] + em) / 2
            status = {r["player_id"]: r for r in il}
            # candidate pool: current-week roster skill players
            pool = []
            if roster is not None:
                rr = roster[(roster.team.replace(T.RENAME) == team) & (roster.week == roster[roster.team.replace(T.RENAME) == team].week.max())]
                rr = rr[rr.position.isin(["QB", "RB", "FB", "WR", "TE"]) & rr.status.isin(["ACT", "RES"])] if "status" in rr else rr
                pool = [(r.gsis_id, "RB" if r.position == "FB" else r.position, r.status) for r in rr.itertuples() if isinstance(r.gsis_id, str)]
            d_raw = dhist.raw(opp, g.gameday)
            cand = []
            for pid, pos, rstatus in pool:
                if rstatus != "ACT":
                    continue
                sh = hist.shares(pid, g.gameday, pos, rates_live)
                if sh["games"] == 0 and pos == "QB":
                    continue
                if sh["games"] == 0 or (sh.get("sh_c_out", 0) + sh.get("sh_t_out", 0)) < 0.01:
                    continue
                stt = status.get(pid, {}).get("status")
                if stt == "Out":
                    cand.append({"player_id": pid, "position": pos, "status": "Out", **sh})
                    continue
                cand.append({"player_id": pid, "position": pos, "status": stt if stt in UNCERTAIN else "Active", **sh})
            if not cand:
                continue
            # QB: only the listed starter gets QB rushing shares
            starter = pred.get(f"{side}_qb_id")
            cand = [c for c in cand if c["position"] != "QB" or c["player_id"] == starter]
            team_opps = om_live.predict(ep, em)
            mr, mc = D.opp_multipliers(d_raw, rates_live)
            for scen_name, avail in (("uncertain_active", {c["player_id"] for c in cand if c["status"] != "Out"}),
                                     ("uncertain_out", {c["player_id"] for c in cand if c["status"] == "Active"})):
                TD.renormalize(cand, avail)
                for c in cand:
                    if c["player_id"] not in avail:
                        c[f"p_{scen_name}"] = None
                        continue
                    hc = D.hist_counts(hist, c["player_id"], g.gameday)
                    eff = D.eff_from(hc, rates_live)
                    lr, lc, eo = TD.TDModel.lambdas(c, team_opps, rates_live, eff, mr, mc)
                    c[f"lam_{scen_name}"] = (lr, lc)
                    c[f"p_{scen_name}"] = float(td_live.prob(pd.DataFrame([{"lam_rush": lr, "lam_rec": lc, "position": c["position"], "games": c["games"]}]))[0])
                    if scen_name == "uncertain_active":
                        c["exp_opps"] = eo; c["eff"] = eff; c["opp_mult"] = (mr, mc)
            for c in cand:
                c.update({"team": team, "opp": opp, "side": side, "exp_points": ep, "exp_margin": em})
            out.extend(cand)
        return out

    def td_confidence(c, qb_unc):
        score, reasons = 0, []
        if c["games"] >= 6:
            score += 1; reasons.append("6+ recent games of usage history")
        elif c["games"] < 3:
            score -= 1; reasons.append("Fewer than 3 recent games: role estimate is thin")
        sr = snap_recent.get(c["player_id"], [])
        if len(sr) >= 3 and (max(sr) - min(sr)) > 0.25:
            score -= 1; reasons.append("Snap share has swung >25 pts over the last 3 games")
        elif len(sr) >= 3:
            score += 1; reasons.append("Stable snap share over the last 3 games")
        if c["status"] in UNCERTAIN:
            score -= 2; reasons.append(f"Listed {c['status']}")
        if qb_unc:
            score -= 1; reasons.append("Team's starting QB is uncertain")
        lab = "High" if score >= 2 else "Medium" if score >= 0 else "Low"
        return {"label": lab, "score": score, "reasons": reasons}

    def td_explain(c, p):
        eo, pos = c["exp_opps"], c["position"]
        i10 = eo["c_i5"] + eo["c_6_10"]
        bits = []
        if pos in ("RB", "QB") and i10 >= 0.3:
            bits.append(f"{i10:.1f} projected carries inside the 10 ({c['sh_c_6_10']*100:.0f}% team share)")
        if eo["t_ez"] + eo["t_rz"] >= 0.3:
            bits.append(f"{eo['t_ez'] + eo['t_rz']:.1f} projected red-zone targets ({eo['t_ez']:.1f} end-zone)")
        if not bits:
            bits.append(f"{sum(eo[z] for z in TD.ZONES_REC):.1f} targets and {sum(eo[z] for z in TD.ZONES_RUSH):.1f} carries projected")
        bits.append(f"team projected for {c['exp_points']:.1f} pts")
        mr, mc = c["opp_mult"]
        lr, lc = c["lam_uncertain_active"]
        m = mr if lr >= lc else mc
        if abs(m - 1) >= 0.1:
            bits.append(f"{c['opp']} defense allows {'more' if m > 1 else 'fewer'} {'rushing' if lr >= lc else 'receiving'} TDs than expected ({(m-1)*100:+.0f}%)")
        if abs(c["eff"] - 1) >= 0.15:
            bits.append(f"finishing rate {'above' if c['eff'] > 1 else 'below'} expectation, shrunk ({(c['eff']-1)*100:+.0f}%)")
        return "; ".join(bits)

    def td_record(c, g, qb_unc, mkt_props):
        p = c.get("p_uncertain_active")
        lr, lc = c["lam_uncertain_active"]
        rec = {"player_id": c["player_id"], "name": name_map.get(c["player_id"], c["player_id"]),
               "headshot": head_map.get(c["player_id"]), "team": c["team"], "opp": c["opp"], "position": c["position"],
               "game_id": g.game_id, "status": c["status"], "p": p, "p_if_uncertain_out": c.get("p_uncertain_out"),
               "p_raw_poisson": TD.raw_poisson_p(lr, lc), "lam_rush": lr, "lam_rec": lc,
               "rush_share_of_td": lr / (lr + lc) if lr + lc else 0,
               "exp_opps": c["exp_opps"], "shares": {k: c[k] for k in c if k.startswith("sh_")},
               "usage": c.get("raw", {}), "finishing_mult": c["eff"], "opp_mult": {"rush": c["opp_mult"][0], "rec": c["opp_mult"][1]},
               "team_exp_points": c["exp_points"], "team_exp_margin": c["exp_margin"],
               "season": plines.get(c["player_id"], {}), "recent": td_recent(c["player_id"], g.gameday, int(g.season)),
               "snap_pct_last3": snap_recent.get(c["player_id"], []),
               "opp_vs_pos": dvp.get(c["opp"], {}).get(c["position"]),
               "confidence": td_confidence(c, qb_unc), "why": td_explain(c, p)}
        mk = None
        if mkt_props:
            nm = re.sub(r"[^a-z]", "", rec["name"].lower())
            for k, books in mkt_props.items():
                if re.sub(r"[^a-z]", "", k.lower()) == nm:
                    best_book, best = max(books.items(), key=lambda kv: O.american_to_decimal(kv[1]))
                    imp = O.american_to_implied(best)
                    dec = O.american_to_decimal(best)
                    mk = {"odds": best, "book": best_book, "raw_implied": imp,
                          "edge_pp": (p - imp) * 100, "ev_per_unit": O.expected_profit(p, dec), "roi_pct": O.roi_pct(p, dec),
                          "note": "Single-sided market: margin cannot be removed exactly; edge is vs raw implied probability."}
        rec["market"] = mk
        return rec

    # ------------------------------------------------- assemble current & future weeks
    sched_cur = games[games.season == season].sort_values(["gameday", "gametime"])
    gp_all_live = gp_live.set_index("game_id")
    week_files = []
    all_td_current = []
    for wk, wg in sched_cur.groupby("week"):
        recs, tds = [], []
        for g in wg.itertuples(index=False):
            gser = pd.Series(g._asdict())
            if not pd.isna(g.home_score) or g.game_id not in gp_all_live.index:
                # played: walk-forward backtest prediction for this season
                if g.game_id not in gp_bt_i.index:
                    continue
                pr = gp_bt_i.loc[g.game_id].to_dict()
                pr["backtest"] = True
                trS = played[played.season < season]
                pr["model"] = bt_models.setdefault(season, GameModel().fit(trS, trS.margin.values, trS.total.values, f"2017-{season-1}"))
                rec = game_record(gser, pr, full=(wk >= cur_week - 1), week_inj=wk)
                # TD backtest rows for this game
                tb = td_bt[td_bt.game_id == g.game_id]
                for r in tb.sort_values("p", ascending=False).itertuples(index=False):
                    tds.append({"player_id": r.player_id, "name": name_map.get(r.player_id, r.player_id), "team": r.team,
                                "opp": r.opp, "position": r.position, "game_id": r.game_id, "p": float(r.p),
                                "lam_rush": float(r.lam_rush), "lam_rec": float(r.lam_rec), "status": "Played",
                                "scored": int(r.y), "backtest": True, "headshot": head_map.get(r.player_id)})
            else:
                pr = gp_all_live.loc[g.game_id].to_dict()
                full = wk == cur_week
                pr["home_qb_id"] = metas[g.game_id]["qb"]["home"]["id"]
                pr["away_qb_id"] = metas[g.game_id]["qb"]["away"]["id"]
                rec = game_record(gser, pr, full=full, week_inj=wk)
                if full:
                    qb_unc = any(s_["kind"] == "qb" and s_.get("trigger_status") for s_ in rec.get("scenarios", []))
                    cands = td_live_rows(gser, pr, rec["home"].get("injuries", []), rec["away"].get("injuries", []))
                    props = (odds_live.get((g.away_team, g.home_team)) or {}).get("anytime_td") if odds_live else None
                    trs = [td_record(c, gser, qb_unc, props) for c in cands if c.get("p_uncertain_active") is not None]
                    trs = [t for t in trs if t["p"] >= 0.02]
                    ruled_out = [{"player_id": c["player_id"], "name": name_map.get(c["player_id"]), "position": c["position"],
                                  "team": c["team"]} for c in cands if c["status"] == "Out"]
                    lams = [t["lam_rush"] + t["lam_rec"] for t in trs]
                    for t, f1 in zip(trs, TD.first_td_approx(lams)):
                        t["p_first_td_approx"] = f1
                    tds.extend(sorted(trs, key=lambda t: -t["p"]))
                    rec["td_ruled_out"] = ruled_out
                    rec["prediction"]["home_qb_id"] = pr["home_qb_id"]
                    for t in trs:
                        all_td_current.append(t)
                    # prediction log (pre-kickoff only)
                    if rec["kickoff_utc"] > run_id:
                        m = rec["market"] or {}
                        DB.log_game(db, run_id, {"game_id": g.game_id, "kickoff_utc": rec["kickoff_utc"], "home_team": g.home_team,
                                                 "away_team": g.away_team, "p_home": rec["prediction"]["p_home"],
                                                 "exp_margin": rec["prediction"]["exp_margin"], "exp_total": rec["prediction"]["exp_total"],
                                                 "market_p_home": m.get("home_no_vig"), "home_ml": m.get("home_moneyline"),
                                                 "away_ml": m.get("away_moneyline"), "spread_line": m.get("spread_line"),
                                                 "total_line": m.get("total_line"), "confidence": rec["confidence"]["label"],
                                                 "info": {"scenarios": [s["name"] for s in rec.get("scenarios", [])]}})
                        for t in trs:
                            DB.log_td(db, run_id, {"game_id": g.game_id, "player_id": t["player_id"], "player_name": t["name"],
                                                   "team": t["team"], "position": t["position"], "p_anytime": t["p"],
                                                   "lam_rush": t["lam_rush"], "lam_rec": t["lam_rec"], "status": t["status"],
                                                   "market_odds": (t["market"] or {}).get("odds"), "confidence": t["confidence"]["label"]})
                        rec["history"] = DB.history_for_game(db, g.game_id)
            recs.append(rec)
        if not recs:
            continue
        fname = f"{season}_{int(wk):02d}.json"
        write_json(C.OUT_DIR / "weeks" / fname, {"season": season, "week": int(wk), "generated": run_id,
                                                  "is_current": int(wk) == cur_week, "games": recs, "td": tds})
        week_files.append({"season": season, "week": int(wk), "file": f"weeks/{fname}", "games": len(recs),
                           "kind": "current" if wk == cur_week else "past" if wk < cur_week else "lookahead",
                           "label": f"Week {wk}" if wk <= 18 else {19: "Wild Card", 20: "Divisional", 21: "Conference", 22: "Super Bowl"}.get(int(wk), f"Week {wk}")})
        log.info("week %s written (%.0fs)", wk, time.time() - t0)

    # past seasons (walk-forward backtest view)
    for S in range(season - C.HISTORY_SEASONS_IN_UI, season):
        if S < C.BACKTEST_FIRST_SEASON:
            continue
        trS = played[played.season < S]
        mS = GameModel().fit(trS, trS.margin.values, trS.total.values, f"2017-{S-1}")
        bpred = gp_bt.set_index("game_id")
        for wk, wg in games[games.season == S].groupby("week"):
            recs, tds = [], []
            for g in wg.itertuples(index=False):
                if g.game_id not in bpred.index or pd.isna(g.home_score):
                    continue
                pr = bpred.loc[g.game_id].to_dict(); pr["backtest"] = True; pr["model"] = mS
                recs.append(game_record(pd.Series(g._asdict()), pr, full=False, week_inj=None))
                for r in td_bt[td_bt.game_id == g.game_id].sort_values("p", ascending=False).head(30).itertuples(index=False):
                    tds.append({"player_id": r.player_id, "name": name_map.get(r.player_id, r.player_id), "team": r.team,
                                "opp": r.opp, "position": r.position, "game_id": r.game_id, "p": float(r.p),
                                "lam_rush": float(r.lam_rush), "lam_rec": float(r.lam_rec), "status": "Played",
                                "scored": int(r.y), "backtest": True, "headshot": head_map.get(r.player_id)})
            fname = f"{S}_{int(wk):02d}.json"
            write_json(C.OUT_DIR / "weeks" / fname, {"season": S, "week": int(wk), "generated": run_id, "is_current": False,
                                                      "games": recs, "td": tds})
            week_files.append({"season": S, "week": int(wk), "file": f"weeks/{fname}", "games": len(recs), "kind": "past",
                               "label": f"Week {wk}" if wk <= 18 else {19: "Wild Card", 20: "Divisional", 21: "Conference", 22: "Super Bowl"}.get(int(wk), f"Week {wk}")})

    # ------------------------------------------------- results into DB + performance
    pg = games[games.home_score.notna() & games.game_id.isin({r["game_id"] for r in DB.last_pregame_games(db)})]
    if len(pg):
        DB.record_results(db, pg)
        ar = act[act.game_id.isin(pg.game_id)].merge(usage[["game_id", "player_id", "rush_td", "rec_td"]], on=["game_id", "player_id"], how="left").fillna(0)
        ar["scored"] = ((ar.rush_td + ar.rec_td) > 0).astype(int); ar["played"] = 1
        DB.record_results(db, pg.iloc[:0], ar[["game_id", "player_id", "scored", "played"]])
    db.commit()
    from .evaluate import performance
    perf = performance(gf, gp_bt, games, td_bt, db, live, td_live, season)
    write_json(C.OUT_DIR / "performance.json", perf)

    # ------------------------------------------------- meta
    fresh = [{"file": k, **v} for k, v in N.FRESHNESS.items()]
    meta = {
        "generated": run_id, "season": season, "current_week": cur_week, "model_version": C.MODEL_VERSION,
        "weeks": sorted(week_files, key=lambda w: (-w["season"], w["week"])), "teams": team_info,
        "default_min_edge_pp": C.DEFAULT_MIN_EDGE_PP, "odds_source": odds_source,
        "odds_error": odds_live.get("_error") if isinstance(odds_live, dict) else None,
        "td_market_available": bool(odds_live and C.ODDS_API_TD_PROPS),
        "weather_enabled": not args.no_weather,
        "sources": fresh,
        "features": {
            "live": ["Schedule, scores, consensus moneyline/spread/total (nflverse)", "Play-by-play & EPA (nflverse)",
                     "Official injury report & practice participation (nflverse)", "Snap counts (nflverse/PFR)",
                     "Depth charts (nflverse/ESPN)", "FTN charting: play action, motion, blitz, box (nflverse)"] +
                    (["Weather forecasts (Open-Meteo)"] if not args.no_weather else []) +
                    (["Live sportsbook odds (The Odds API)"] if odds_source == "the-odds-api" else []),
            "unavailable": (["Weather forecasts (disabled for this build)"] if args.no_weather else []) +
                           ([] if odds_source == "the-odds-api" else ["Live multi-book odds (set ODDS_API_KEY)"]) +
                           ([] if odds_live and C.ODDS_API_TD_PROPS else ["Anytime-TD sportsbook odds (paid odds plan)"]) +
                           ["Man/zone & single-high/two-high coverage (licensed charting data)", "Route participation (licensed data)"],
        },
        "methodology": {
            "game": {"trained_on": live.train_span, "n_train": live.n_train, "sigma_margin": live.sigma_margin,
                     "sigma_total": live.sigma_total, "coefficients": live.coef_table()},
            "td": {"rates_per_opportunity": rates_live, "calibration": td_live.calib_coefs(), "n_calibration": td_live.n_train,
                   "team_opportunity_model": om_live.coefs},
        },
        "build_seconds": round(time.time() - t0),
    }
    write_json(C.OUT_DIR / "meta.json", meta)
    db.close()
    log.info("done in %.0fs", time.time() - t0)


bt_models: dict = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-weather", action="store_true", help="skip weather API calls")
    ap.add_argument("--rebuild", action="store_true", help="rebuild cached TD rows")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args)


if __name__ == "__main__":
    main()
