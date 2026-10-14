"""Weekly retrain.

Runs once per completed week (after Monday night is final). It:
  1. replays 2021 -> last completed week as a week-by-week walk-forward: every week is predicted by a
     model trained only on games before it, so the score is out-of-sample;
  2. tries a small grid of settings: how fast this season's data overrides last season's
     (k_mult, prior_regress), the ridge penalty (alpha) and recency weighting (half_life);
  3. keeps the current settings unless a challenger is better both on 2021 through last season AND on
     the current season to date, so it doesn't chase noise in a handful of weeks;
  4. writes data/model_params.json (used by every build) and a report in data/models/.

The week-level game model itself is refit on every build with all completed games.

    python -m nfledge.retrain           # no-op if already done for the latest completed week
    python -m nfledge.retrain --force
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config as C
from . import features as F
from . import odds as O
from . import teamdata as T
from .models.game_model import GameModel

log = logging.getLogger("nfledge.retrain")
PARAMS_PATH = C.DB_PATH.parent / "model_params.json"
REPORT_DIR = C.DB_PATH.parent / "models"
DEFAULT = {"rating": {"k_mult": 1.0, "prior_regress": 0.5}, "model": {"alpha": 25.0, "logit_c": 0.05, "half_life": None}}
GRID_RATING = [{"k_mult": k, "prior_regress": p} for k, p in itertools.product([0.6, 1.0, 1.5], [0.35, 0.5, 0.65])]
GRID_MODEL = [{"alpha": a, "logit_c": 0.05, "half_life": h} for a, h in itertools.product([10.0, 25.0, 60.0], [None, 3.0])]
MIN_GAIN = 0.0005     # log-loss improvement needed on both periods before switching


def load_params() -> dict:
    if PARAMS_PATH.exists():
        return json.loads(PARAMS_PATH.read_text())
    return {**DEFAULT, "version": "game-v1.0", "trained_through": None, "history": []}


def last_completed_week(games: pd.DataFrame, pbp: pd.DataFrame, season: int) -> int | None:
    g = games[(games.season == season)]
    done = []
    have = set(pbp.game_id.unique())
    for wk, x in g.groupby("week"):
        if x.home_score.notna().all() and x.game_id.isin(have).all():
            done.append(int(wk))
    # completed weeks must be a prefix of the season
    w = 0
    for wk in sorted(done):
        if wk == w + 1:
            w = wk
    return w or None


def walk_forward(gf: pd.DataFrame, first: int, **mp) -> pd.DataFrame:
    played = gf[gf.played]
    out = []
    for (S, wk), te in played[played.season >= first].groupby(["season", "week"]):
        tr = played[(played.season < S) | ((played.season == S) & (played.week < wk))]
        p = GameModel(**mp).fit(tr, tr.margin.values, tr.total.values).predict(te)
        out.append(te[["game_id", "season", "week", "margin", "total"]].reset_index(drop=True)
                   .join(p[["p_home", "exp_margin", "exp_total"]].reset_index(drop=True)))
    return pd.concat(out, ignore_index=True)


def _ll(y, p):
    p = np.clip(np.asarray(p, float), 1e-3, 1 - 1e-3)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def score(r: pd.DataFrame) -> dict:
    r = r[r.margin != 0]
    if r.empty:
        return {}
    y = (r.margin > 0).astype(int).values
    return {"n": int(len(r)), "log_loss": _ll(y, r.p_home), "accuracy": float(((r.p_home > .5) == y).mean()),
            "margin_mae": float((r.margin - r.exp_margin).abs().mean()), "total_mae": float((r.total - r.exp_total).abs().mean())}


def market_p(games: pd.DataFrame) -> dict:
    out = {}
    for r in games.itertuples(index=False):
        if pd.notna(r.home_moneyline) and pd.notna(r.away_moneyline):
            out[r.game_id] = O.remove_vig_proportional([O.american_to_implied(r.home_moneyline), O.american_to_implied(r.away_moneyline)])[0]
    return out


def run(force: bool = False) -> dict | None:
    t0 = time.time()
    games, pbp, season = T.load()
    W = last_completed_week(games, pbp, season)
    cur = load_params()
    tt = cur.get("trained_through")
    if not force and W and tt and (tt["season"], tt["week"]) >= (season, W):
        log.info("retrain: already trained through %s week %s", season, W)
        return None
    if not W:
        log.info("retrain: no completed week yet in %s", season)
        return None
    games = games[(games.season < season) | (games.week <= W)]       # nothing from future weeks
    tgs = F.team_game_stats(pbp, games)
    inc_key = (json.dumps(cur["rating"], sort_keys=True), json.dumps(cur["model"], sort_keys=True))
    results, frames = [], {}
    for rp in GRID_RATING:
        gf, *_ = T.build_game_frame(games, pbp, 2017, rp, tgs=tgs)
        for mp in GRID_MODEL:
            r = walk_forward(gf, C.BACKTEST_FIRST_SEASON, **mp)
            key = (json.dumps(rp, sort_keys=True), json.dumps(mp, sort_keys=True))
            if key == inc_key:
                frames["incumbent"] = r
            results.append({"rating": rp, "model": mp, "prior": score(r[r.season < season]), "current": score(r[r.season == season]),
                            "_r": r})
        log.info("retrain: rating %s done (%.0fs)", rp, time.time() - t0)
    if "incumbent" not in frames:          # incumbent outside the grid: evaluate it too
        gf, *_ = T.build_game_frame(games, pbp, 2017, cur["rating"], tgs=tgs)
        r = walk_forward(gf, C.BACKTEST_FIRST_SEASON, **cur["model"])
        results.append({"rating": cur["rating"], "model": cur["model"], "prior": score(r[r.season < season]),
                        "current": score(r[r.season == season]), "_r": r})
        frames["incumbent"] = r
    inc = next(x for x in results if (json.dumps(x["rating"], sort_keys=True), json.dumps(x["model"], sort_keys=True)) == inc_key)
    ok = [x for x in results if x["prior"]["log_loss"] <= inc["prior"]["log_loss"] - MIN_GAIN
          and x["current"]["log_loss"] <= inc["current"]["log_loss"] - MIN_GAIN]
    best = min(ok, key=lambda x: x["prior"]["log_loss"] + x["current"]["log_loss"]) if ok else inc
    changed = best is not inc

    # week-by-week, current season, chosen settings vs the market
    mk = market_p(games)
    r = best["_r"]
    weekly = []
    for wk, x in r[(r.season == season) & (r.margin != 0)].groupby("week"):
        y = (x.margin > 0).astype(int).values
        m = np.array([mk.get(g, np.nan) for g in x.game_id])
        ok_m = ~np.isnan(m)
        weekly.append({"week": int(wk), "games": int(len(x)), "model_correct": int(((x.p_home > .5) == y).sum()),
                       "market_correct": int(((m[ok_m] > .5) == y[ok_m]).sum()), "model_log_loss": _ll(y, x.p_home),
                       "market_log_loss": _ll(y[ok_m], m[ok_m]) if ok_m.any() else None})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_minor = int(cur.get("version", "game-v1.0").split(".")[-1]) + (1 if changed else 0)
    version = f"game-v1.{n_minor}"
    strip = lambda x: {k: v for k, v in x.items() if k != "_r"}
    report = {"season": season, "trained_through_week": W, "for_week": W + 1, "generated": now, "version": version,
              "changed": changed, "incumbent": strip(inc), "chosen": strip(best),
              "rule": f"switch only if log loss improves by at least {MIN_GAIN} on both {C.BACKTEST_FIRST_SEASON}-{season-1} and {season} to date",
              "grid": sorted([strip(x) for x in results], key=lambda x: x["prior"]["log_loss"] + x["current"]["log_loss"])[:10],
              "weekly_current_season": weekly, "games_in_training": int(len(games[games.home_score.notna()])),
              "seconds": round(time.time() - t0)}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{season}_wk{W+1:02d}.json").write_text(json.dumps(report, indent=1))
    hist = cur.get("history", []) + [{"for_week": f"{season}_{W+1:02d}", "generated": now, "version": version, "changed": changed,
                                      "rating": best["rating"], "model": best["model"],
                                      "prior_log_loss": best["prior"]["log_loss"], "current_log_loss": best["current"]["log_loss"]}]
    PARAMS_PATH.write_text(json.dumps({"version": version, "trained_through": {"season": season, "week": W}, "updated": now,
                                       "rating": best["rating"], "model": best["model"], "history": hist[-40:]}, indent=1))
    log.info("retrain: %s (changed=%s) through %s wk%s in %.0fs", version, changed, season, W, time.time() - t0)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(a.force)


if __name__ == "__main__":
    main()
