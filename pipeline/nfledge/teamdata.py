"""Loads schedule + play-by-play and assembles the leak-free game feature frame."""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from . import features as F
from .config import PBP_FIRST_SEASON
from .ingest import nflverse
from .models import elo as elo_mod
from .models.game_model import QBRater, game_features

log = logging.getLogger(__name__)
RENAME = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def norm_team(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df:
            df[c] = df[c].replace(RENAME)
    return df


def current_season(games: pd.DataFrame, today: date | None = None) -> int:
    today = today or date.today()
    s = today.year if today.month >= 3 else today.year - 1
    return int(min(s, games.season.max()))


def load(today: date | None = None):
    games = nflverse.schedules()
    games = norm_team(games, ["home_team", "away_team"])
    season = current_season(games, today)
    frames = []
    for s in range(PBP_FIRST_SEASON, season + 1):
        frames.append(nflverse.pbp(s, current=(s == season)))
    pbp = pd.concat(frames, ignore_index=True)
    pbp = norm_team(pbp, ["posteam", "defteam", "home_team", "away_team", "td_team"])
    return games, pbp, season


def build_game_frame(games: pd.DataFrame, pbp: pd.DataFrame, first_season: int):
    tgs = F.team_game_stats(pbp, games)
    rater = F.TeamRater(tgs)
    qbr = QBRater(F.qb_game_epa(pbp), games)
    elo_df, elo_now = elo_mod.run(games)
    elo_df["elo_diff_nohfa"] = elo_df.home_elo - elo_df.away_elo
    elo_map = elo_df.set_index("game_id").to_dict("index")
    venue_cache: dict = {}
    rows, metas = [], {}
    sel = games[(games.season >= first_season)].sort_values(["gameday", "game_id"])
    for g in sel.itertuples(index=False):
        gs = pd.Series(g._asdict())
        fe = game_features(gs, games, rater, qbr, elo_map[g.game_id], venue_cache)
        r = {"game_id": g.game_id, "season": g.season, "week": g.week, "game_type": g.game_type,
             "gameday": g.gameday, "home_team": g.home_team, "away_team": g.away_team,
             "home_score": g.home_score, "away_score": g.away_score, **fe["x"],
             "elo_prob": elo_map[g.game_id]["elo_prob"]}
        rows.append(r)
        metas[g.game_id] = fe["meta"]
    gf = pd.DataFrame(rows)
    gf["margin"] = gf.home_score - gf.away_score
    gf["total"] = gf.home_score + gf.away_score
    gf["played"] = gf.home_score.notna()
    return gf, metas, tgs, rater, qbr, elo_df, elo_now, venue_cache
