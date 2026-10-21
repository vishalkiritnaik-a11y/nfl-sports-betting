"""Wong-teaser screen: 6-point teaser legs that cross both 3 and 7.

  favorite legs: favored by 7.5-8.5, teased down to -1.5..-2.5
  underdog legs: getting 1.5-2.5, teased up to +7.5..+8.5

The historical record is measured against the closing consensus spread (nflverse), pushes excluded.
A 2-team teaser at American price A needs each leg to hit sqrt(1 / decimal(A)) of the time.
"""
from __future__ import annotations

import math

import pandas as pd

TEASE = 6.0
FAV = (7.5, 8.5)
DOG = (1.5, 2.5)
PRICES = (-110, -120, -130, -140)
RECENT_SEASONS = 4      # current season plus the 3 before it


def kind_for(exp_margin: float | None) -> str | None:
    """exp_margin = how many points this side is favored by (negative = underdog)."""
    if exp_margin is None or (isinstance(exp_margin, float) and math.isnan(exp_margin)):
        return None
    if FAV[0] <= exp_margin <= FAV[1]:
        return "fav"
    if DOG[0] <= -exp_margin <= DOG[1]:
        return "dog"
    return None


def break_even_leg(american: float) -> float:
    dec = 1 + (100 / abs(american) if american < 0 else american / 100)
    return math.sqrt(1 / dec)


def legs(games: pd.DataFrame) -> pd.DataFrame:
    """Every qualifying historical leg. games.spread_line = expected home margin (nflverse)."""
    g = games[games.home_score.notna() & games.spread_line.notna()]
    m = g.home_score - g.away_score
    out = []
    for side, sign in (("home", 1), ("away", -1)):
        exp, mg = sign * g.spread_line, sign * m
        k = exp.map(kind_for)
        x = pd.DataFrame({"season": g.season, "kind": k, "res": mg - exp + TEASE})[k.notna()]
        out.append(x)
    x = pd.concat(out, ignore_index=True)
    x = x[x.res != 0]
    x["hit"] = x.res > 0
    return x


def _rate(x: pd.DataFrame) -> dict:
    return {"n": int(len(x)), "hit": float(x.hit.mean()) if len(x) else None}


def record(games: pd.DataFrame, season: int, first_season: int = 2016) -> dict:
    x = legs(games[games.season >= first_season])
    rec = x[x.season > season - RECENT_SEASONS]
    return {
        "tease": TEASE, "fav_range": FAV, "dog_range": DOG,
        "periods": {"all": {"from": first_season, "to": season}, "recent": {"from": season - RECENT_SEASONS + 1, "to": season}},
        "all": {"fav": _rate(x[x.kind == "fav"]), "dog": _rate(x[x.kind == "dog"]), "both": _rate(x)},
        "recent": {"fav": _rate(rec[rec.kind == "fav"]), "dog": _rate(rec[rec.kind == "dog"]), "both": _rate(rec)},
        "break_even": {str(p): break_even_leg(p) for p in PRICES},
    }
