"""Feature engineering: team-game box stats from play-by-play, pre-game
(leak-free) blended team ratings, QB ratings, travel/rest context.

Every pre-game feature for a game uses ONLY games that kicked off earlier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import stadiums

# Blending constants: weight of the prior in "denominator units".
K_PLAYS = 350        # ~5.5 games of plays before current season dominates
K_GAMES = 5          # for per-game stats
K_DROPBACKS_QB = 250
PRIOR_REGRESS = 0.5  # prior = 0.5 * last season + 0.5 * league mean
QB_REPLACEMENT_EPA = -0.12  # prior for a QB with no history (approx. backup-level EPA/dropback)

RATE_FEATURES = {
    # name: (numerator, denominator, K)
    "epa_play": ("epa_sum", "plays", K_PLAYS),
    "success": ("success_sum", "plays", K_PLAYS),
    "pass_epa": ("pass_epa_sum", "dropbacks", K_PLAYS * 0.6),
    "rush_epa": ("rush_epa_sum", "rushes", K_PLAYS * 0.4),
    "explosive": ("explosive", "plays", K_PLAYS),
    "ypp": ("yards", "plays", K_PLAYS),
    "third_conv": ("third_conv", "third_att", 60),
    "fourth_conv": ("fourth_conv", "fourth_att", 15),
    "rz_td": ("rz_td_drives", "rz_drives", 25),
    "to_rate": ("turnovers", "plays", K_PLAYS * 2),
    "sack_rate": ("sacks", "dropbacks", K_PLAYS * 0.6),
    "pressure_rate": ("pressures", "dropbacks", K_PLAYS * 0.6),
    "st_epa": ("st_epa", "games", K_GAMES),
    "points": ("points", "games", K_GAMES),
    "plays_pg": ("plays", "games", K_GAMES),
    "top_min": ("top_sec", "games", K_GAMES),
    "pass_rate": ("dropbacks", "plays", K_PLAYS),
}


def _mmss(s: str | float) -> float:
    if not isinstance(s, str) or ":" not in s:
        return 0.0
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def team_game_stats(pbp: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team) with offensive count stats; defensive stats
    are the opponent's offensive row joined later."""
    p = pbp[(pbp.season_type.isin(["REG", "POST"]))].copy()
    scrim = p[(p.play_type.isin(["pass", "run"])) & (p.two_point_attempt != 1) & p.epa.notna() & p.posteam.notna()].copy()
    scrim["explosive_f"] = (((scrim["pass"] == 1) & (scrim.yards_gained >= 20)) | ((scrim["rush"] == 1) & (scrim.yards_gained >= 10))).astype(int)
    scrim["to_f"] = scrim.interception.fillna(0) + scrim.fumble_lost.fillna(0)
    scrim["press_f"] = ((scrim.sack == 1) | (scrim.qb_hit == 1)).astype(int)
    scrim["db"] = scrim.qb_dropback.fillna(0)
    scrim["ru"] = ((scrim["rush"] == 1) & (scrim.qb_scramble != 1)).astype(int)
    g = scrim.groupby(["game_id", "posteam"])
    off = pd.DataFrame({
        "plays": g.size(),
        "epa_sum": g.epa.sum(),
        "success_sum": g.success.sum(),
        "dropbacks": g.db.sum(),
        "pass_epa_sum": g.apply(lambda d: d.epa[d.db == 1].sum(), include_groups=False),
        "rushes": g.ru.sum(),
        "rush_epa_sum": g.apply(lambda d: d.epa[d.ru == 1].sum(), include_groups=False),
        "explosive": g.explosive_f.sum(),
        "yards": g.yards_gained.sum(),
        "turnovers": g.to_f.sum(),
        "sacks": g.sack.sum(),
        "pressures": g.press_f.sum(),
    })
    third = p[(p.down == 3) & p.play_type.isin(["pass", "run"])].groupby(["game_id", "posteam"])
    off["third_att"] = third.size()
    off["third_conv"] = third.third_down_converted.sum()
    fourth = p[(p.down == 4) & p.play_type.isin(["pass", "run"])].groupby(["game_id", "posteam"])
    off["fourth_att"] = fourth.size()
    off["fourth_conv"] = fourth.fourth_down_converted.sum()
    # red zone drives: drives that reached the 20, and how many ended in a TD
    dr = p[p.posteam.notna() & p.fixed_drive.notna()].groupby(["game_id", "posteam", "fixed_drive"]).agg(
        min_yl=("yardline_100", "min"), res=("fixed_drive_result", "last"), top=("drive_time_of_possession", "first"))
    dr["rz"] = dr.min_yl <= 20
    dr["rz_td"] = dr.rz & (dr.res == "Touchdown")
    dr["top_s"] = dr.top.map(_mmss)
    d2 = dr.groupby(["game_id", "posteam"])
    off["rz_drives"] = d2.rz.sum()
    off["rz_td_drives"] = d2.rz_td.sum()
    off["drives"] = d2.size()
    off["top_sec"] = d2.top_s.sum() / 60.0  # minutes
    st = p[p.special_teams_play == 1].copy()
    st_pos = st.groupby(["game_id", "posteam"]).epa.sum()
    st_def = st.groupby(["game_id", "defteam"]).epa.sum()
    st_def.index = st_def.index.set_names(["game_id", "posteam"])
    off["st_epa"] = st_pos.sub(st_def, fill_value=0)
    off = off.fillna(0).reset_index().rename(columns={"posteam": "team"})

    # points & opponent from schedule
    gs = games[["game_id", "season", "week", "gameday", "home_team", "away_team", "home_score", "away_score"]]
    h = gs.rename(columns={"home_team": "team", "away_team": "opp", "home_score": "points", "away_score": "points_allowed"})
    a = gs.rename(columns={"away_team": "team", "home_team": "opp", "away_score": "points", "home_score": "points_allowed"})
    sched = pd.concat([h, a])
    off = off.merge(sched, on=["game_id", "team"], how="inner")
    off["games"] = 1
    # defensive (allowed) = opponent's offensive row
    cnt = [c for c in off.columns if c not in ("game_id", "team", "opp", "season", "week", "gameday", "points_allowed")]
    d = off[["game_id", "team"] + cnt].rename(columns={"team": "opp", **{c: f"d_{c}" for c in cnt}})
    out = off.merge(d, on=["game_id", "opp"], how="left")
    return out.sort_values(["gameday", "game_id"]).reset_index(drop=True)


def _league_rates(tgs: pd.DataFrame, side: str = "") -> dict:
    res = {}
    for f, (num, den, _) in RATE_FEATURES.items():
        n, d = tgs[f"{side}{num}"].sum(), tgs[f"{side}{den}"].sum()
        res[f] = n / d if d else np.nan
    return res


class TeamRater:
    """Leak-free blended team ratings as of any date."""

    def __init__(self, tgs: pd.DataFrame, k_mult: float = 1.0, prior_regress: float = PRIOR_REGRESS):
        """k_mult scales how many plays/games of last-season prior a team carries (higher = slower to
        trust the current season); prior_regress is the share of last season kept in that prior."""
        self.tgs = tgs
        self.k_mult, self.prior_regress = k_mult, prior_regress
        self.by_team = {t: d.sort_values("gameday") for t, d in tgs.groupby("team")}
        self.league = {}
        for s in sorted(tgs.season.unique()):
            x = tgs[tgs.season == s]
            self.league[s] = (_league_rates(x), _league_rates(x, "d_"))

    def _lg(self, season: int):
        if season - 1 in self.league:
            return self.league[season - 1]
        return self.league[max(k for k in self.league if k <= season)] if any(k <= season for k in self.league) else next(iter(self.league.values()))

    def rate(self, team: str, season: int, before: str) -> dict:
        tg = self.by_team.get(team, self.tgs.iloc[:0])
        cur = tg[(tg.season == season) & (tg.gameday < before)]
        prev = tg[tg.season == season - 1]
        lgs = self._lg(season)
        rec = {"n_games": int(len(cur))}
        for side, pre in (("o", ""), ("d", "d_")):
            lg = lgs[0 if side == "o" else 1]
            for f, (num, den, k) in RATE_FEATURES.items():
                pn, pd_ = prev[f"{pre}{num}"].sum(), prev[f"{pre}{den}"].sum()
                last = pn / pd_ if pd_ else lg[f]
                prior = self.prior_regress * last + (1 - self.prior_regress) * lg[f]
                k = k * self.k_mult
                cn, cd = cur[f"{pre}{num}"].sum(), cur[f"{pre}{den}"].sum()
                rec[f"{side}_{f}"] = float((cn + k * prior) / (cd + k))
        return rec

    def season_raw(self, team: str, season: int, before: str) -> dict:
        """Unblended season-to-date numbers for display."""
        tg = self.by_team.get(team, self.tgs.iloc[:0])
        cur = tg[(tg.season == season) & (tg.gameday < before)]
        if cur.empty:
            return {"games": 0}
        out = {"games": int(len(cur))}
        for side, pre in (("o", ""), ("d", "d_")):
            for f, (num, den, _) in RATE_FEATURES.items():
                d = cur[f"{pre}{den}"].sum()
                out[f"{side}_{f}"] = float(cur[f"{pre}{num}"].sum() / d) if d else None
        out["to_diff"] = float(cur.d_turnovers.sum() - cur.turnovers.sum())
        return out


def recent_form(tgs: pd.DataFrame, team: str, before: str, ns=(3, 5, 10)) -> dict:
    """Raw (unblended) recent form for display; includes previous season games
    when the current season is short, and says so."""
    t = tgs[(tgs.team == team) & (tgs.gameday < before)].sort_values("gameday")
    out = {}
    for n in ns:
        x = t.tail(n)
        if x.empty:
            continue
        out[f"last{n}"] = {
            "games": int(len(x)),
            "spans_prior_season": bool(x.season.nunique() > 1),
            "epa_play": float(x.epa_sum.sum() / max(1, x.plays.sum())),
            "def_epa_play": float(x.d_epa_sum.sum() / max(1, x.d_plays.sum())),
            "points_pg": float(x.points.mean()),
            "points_allowed_pg": float(x.d_points.mean()),
            "success": float(x.success_sum.sum() / max(1, x.plays.sum())),
            "record": f"{int((x.points > x.d_points).sum())}-{int((x.points < x.d_points).sum())}"
                      + (f"-{int((x.points == x.d_points).sum())}" if (x.points == x.d_points).any() else ""),
        }
    return out


# ---------------------------------------------------------------- QB ratings

def qb_game_epa(pbp: pd.DataFrame) -> pd.DataFrame:
    """Per QB per game: dropbacks and EPA (pass + scrambles + sacks)."""
    p = pbp[(pbp.qb_dropback == 1) & pbp.epa.notna() & pbp.passer_player_id.notna() & (pbp.two_point_attempt != 1)]
    q = p.groupby(["game_id", "passer_player_id"]).agg(db=("epa", "size"), epa=("epa", "sum"),
                                                      team=("posteam", "first")).reset_index()
    return q.rename(columns={"passer_player_id": "qb_id"})


def qb_rating_before(qb_games: pd.DataFrame, game_dates: pd.Series, qb_id: str, before: str) -> tuple[float, int]:
    """Blended EPA/dropback for a QB using games before ``before`` (last ~2 seasons,
    weighted toward recent), shrunk toward replacement level."""
    if not isinstance(qb_id, str):
        return QB_REPLACEMENT_EPA, 0
    q = qb_games[(qb_games.qb_id == qb_id)]
    q = q[q.gameday < before]
    if q.empty:
        return QB_REPLACEMENT_EPA, 0
    q = q.sort_values("gameday").tail(34)
    w = 0.97 ** np.arange(len(q))[::-1]
    db = float((q.db * w).sum())
    epa = float((q.epa * w).sum())
    return (epa + K_DROPBACKS_QB * QB_REPLACEMENT_EPA) / (db + K_DROPBACKS_QB), int(q.db.sum())


# ------------------------------------------------------------- game context

def team_home_venue(games: pd.DataFrame, team: str, season: int) -> str:
    h = games[(games.home_team == team) & (games.season == season) & (games.location == "Home")]
    if len(h):
        return h.stadium_id.mode().iloc[0]
    h = games[(games.home_team == team) & (games.location == "Home") & (games.season < season)]
    if len(h):
        return h.sort_values("gameday").stadium_id.iloc[-1]
    return stadiums.TEAM_HOME.get(team, "")


def _tz_offset(tz: str, date: str) -> float:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    d = datetime.fromisoformat(date).replace(hour=13, tzinfo=ZoneInfo(tz))
    return d.utcoffset().total_seconds() / 3600


def context_features(g: pd.Series, games: pd.DataFrame, home_venue_cache: dict) -> dict:
    venue = stadiums.info(g.stadium_id, g.get("stadium")) or {}
    neutral = g.location == "Neutral"
    out = {"neutral": int(neutral), "home_field": 0 if neutral else 1,
           "div_game": int(g.div_game == 1)}
    for side in ("home", "away"):
        team = g[f"{side}_team"]
        key = (team, g.season)
        if key not in home_venue_cache:
            home_venue_cache[key] = team_home_venue(games, team, g.season)
        hv = stadiums.info(home_venue_cache[key])
        if hv and venue:
            km = stadiums.haversine_km(hv["lat"], hv["lon"], venue["lat"], venue["lon"])
            tzd = _tz_offset(venue["tz"], g.gameday) - _tz_offset(hv["tz"], g.gameday)
        else:
            km, tzd = 0.0, 0.0
        out[f"{side}_travel_km"] = km
        out[f"{side}_tz_shift"] = tzd
        rest = g.get(f"{side}_rest")
        out[f"{side}_rest"] = float(rest) if pd.notna(rest) else 7.0
    out["rest_diff"] = float(np.clip(out["home_rest"] - out["away_rest"], -7, 7))
    out["travel_diff_1000km"] = (out["away_travel_km"] - out["home_travel_km"]) / 1000.0
    out["tz_diff"] = abs(out["away_tz_shift"]) - abs(out["home_tz_shift"])
    out["altitude_home"] = int((venue.get("elevation_m", 0) or 0) > 1500 and not neutral)
    # weather (outdoor only). Observed for past games, forecast for upcoming.
    roof = str(g.roof) if pd.notna(g.roof) else ""
    outdoor = roof in ("outdoors", "open") or (roof == "" and venue.get("roof_type") == "outdoor")
    temp, wind = g.get("temp"), g.get("wind")
    out["outdoor"] = int(outdoor)
    out["wind_excess"] = float(max(0.0, (wind if pd.notna(wind) else 0) - 10)) if outdoor else 0.0
    out["cold_excess"] = float(max(0.0, 40 - temp)) if outdoor and pd.notna(temp) else 0.0
    return out
