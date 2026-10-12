"""Market anchoring.

Backtests showed that when the game model disagrees with the closing line, results track
the market, not the model. So value flags use a market-anchored probability:

    logit(p_anchored) = c + a * logit(p_market_novig) + b * (logit(p_model) - logit(p_market_novig))

fit by logistic regression per market (moneyline / spread / total) on walk-forward backtest
sides from seasons before the one being predicted. `b` measures how much of the model's
disagreement is real information; when it is ~0 the anchored probability ~= the market's
and no value is flagged.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import odds as O


def _lg(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def backtest_sides(gp_bt: pd.DataFrame, gf: pd.DataFrame, games: pd.DataFrame, sigma_m: float, sigma_t: float) -> pd.DataFrame:
    """One row per (game, market): model prob for the home/over side, no-vig market prob, outcome."""
    cols = ["game_id", "home_moneyline", "away_moneyline", "spread_line", "home_spread_odds", "away_spread_odds",
            "total_line", "over_odds", "under_odds"]
    b = gp_bt.merge(gf[["game_id", "season", "margin", "total", "played"]], on="game_id").merge(games[cols], on="game_id")
    b = b[b.played]
    rows = []
    for r in b.itertuples(index=False):
        def add(mkt, p, oa, ob, win, push):
            if pd.isna(oa) or pd.isna(ob) or push:
                return
            nv = O.remove_vig_proportional([O.american_to_implied(oa), O.american_to_implied(ob)])[0]
            rows.append({"season": r.season, "market": mkt, "p": p, "mp": nv, "win": int(win)})
        add("moneyline", r.p_home, r.home_moneyline, r.away_moneyline, r.margin > 0, r.margin == 0)
        if not pd.isna(r.spread_line):
            d = r.margin - r.spread_line
            add("spread", 1 - norm.cdf((r.spread_line - r.exp_margin) / sigma_m), r.home_spread_odds, r.away_spread_odds, d > 0, d == 0)
        if not pd.isna(r.total_line):
            d = r.total - r.total_line
            add("total", 1 - norm.cdf((r.total_line - r.exp_total) / sigma_t), r.over_odds, r.under_odds, d > 0, d == 0)
    return pd.DataFrame(rows)


def _fit_b(off: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    """Logistic regression with the market logit as a fixed offset: one free coefficient, b."""
    from scipy.optimize import minimize_scalar

    def nll(b):
        z = off + b * x
        return float(np.sum(np.logaddexp(0, z) - y * z))
    return float(minimize_scalar(nll, bounds=(-3, 3), method="bounded").x)


def fit(sides: pd.DataFrame) -> dict:
    """{market: {"c","a","b","n","b_ci90"}}. The market is taken at face value (c=0, a=1): fitting a free
    slope on spread/total prices mostly fits juice noise around 50%. Only b, the weight on the model's
    disagreement with the market, is estimated."""
    out = {}
    for mkt, d in sides.groupby("market"):
        off, x, y = _lg(d.mp), _lg(d.p) - _lg(d.mp), d.win.values.astype(float)
        b = _fit_b(off, x, y)
        rng = np.random.default_rng(0)
        bs = []
        for _ in range(200):
            i = rng.integers(0, len(d), len(d))
            bs.append(_fit_b(off[i], x[i], y[i]))
        out[mkt] = {"c": 0.0, "a": 1.0, "b": b, "n": int(len(d)),
                    "b_ci90": [float(np.percentile(bs, 5)), float(np.percentile(bs, 95))]}
    return out


def anchored(coef: dict | None, market: str, p_model: float, p_market: float) -> float:
    """Anchored probability for one side. Falls back to the market if no coefficients."""
    if not coef or market not in coef:
        return p_market
    k = coef[market]
    b = max(0.0, k["b"])   # never fade the model on weak evidence: a negative fit is treated as "no information"
    z = k["c"] + k["a"] * float(_lg(p_market)) + b * (float(_lg(p_model)) - float(_lg(p_market)))
    return 1 / (1 + math.exp(-z))
