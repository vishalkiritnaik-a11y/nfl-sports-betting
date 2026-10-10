"""Margin-aware Elo (FiveThirtyEight-style), run from 1999 so ratings are warm.

pre-game ratings are recorded before each update, so they are leak-free.
"""
from __future__ import annotations

import math

import pandas as pd

K = 20.0
HFA = 48.0            # Elo points for a true home game (~1.7 pts)
REVERT = 1 / 3        # off-season regression to 1505
MEAN = 1505.0
ELO_PER_POINT = 25.0  # spread ~= elo_diff / 25


def expected(diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def mov_mult(margin: float, elo_diff_winner: float) -> float:
    return math.log(abs(margin) + 1) * (2.2 / (elo_diff_winner * 0.001 + 2.2))


def run(games: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Returns (per-game pre-game elo, current ratings dict)."""
    g = games.sort_values(["gameday", "game_id"])
    ratings: dict[str, float] = {}
    season_seen: dict[str, int] = {}
    rows = []
    rename = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
    for r in g.itertuples(index=False):
        h, a = rename.get(r.home_team, r.home_team), rename.get(r.away_team, r.away_team)
        for t in (h, a):
            if t not in ratings:
                ratings[t] = MEAN
                season_seen[t] = r.season
            if season_seen[t] != r.season:
                ratings[t] = ratings[t] * (1 - REVERT) + MEAN * REVERT
                season_seen[t] = r.season
        hfa = 0.0 if r.location == "Neutral" else HFA
        diff = ratings[h] + hfa - ratings[a]
        rows.append({"game_id": r.game_id, "home_elo": ratings[h], "away_elo": ratings[a],
                     "elo_diff": diff, "elo_prob": expected(diff)})
        if pd.isna(r.home_score) or pd.isna(r.away_score):
            continue
        margin = r.home_score - r.away_score
        res = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        winner_diff = diff if margin > 0 else -diff
        mult = mov_mult(margin, winner_diff) if margin != 0 else 1.0
        shift = K * mult * (res - expected(diff))
        ratings[h] += shift
        ratings[a] -= shift
    return pd.DataFrame(rows), ratings
