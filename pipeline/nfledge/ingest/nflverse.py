"""Download + cache nflverse release files and record their freshness.

nflverse (https://github.com/nflverse/nflverse-data) is free, CC-BY 4.0 licensed
(play-by-play derived from the NFL's public game data), and is refreshed nightly
(more often on game days). Every file is fetched over HTTPS with its
``Last-Modified`` header captured for the data-freshness panel.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd
import requests

from ..config import CACHE_DIR, NFLVERSE_BASE

log = logging.getLogger(__name__)
FRESHNESS: dict[str, dict] = {}
_META_FILE = CACHE_DIR / "_freshness.json"


def _load_meta() -> dict:
    if _META_FILE.exists():
        return json.loads(_META_FILE.read_text())
    return {}


def _save_meta(meta: dict) -> None:
    _META_FILE.parent.mkdir(parents=True, exist_ok=True)
    _META_FILE.write_text(json.dumps(meta, indent=1))


def fetch(tag: str, filename: str, max_age_hours: float = 3.0, required: bool = True) -> Path | None:
    """Return a local path for ``{tag}/{filename}``, downloading when the cached
    copy is older than ``max_age_hours``. Historic seasons never change so pass
    ``max_age_hours=float('inf')`` for them."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / filename
    meta = _load_meta()
    url = f"{NFLVERSE_BASE}/{tag}/{filename}"
    fresh_enough = dest.exists() and (time.time() - dest.stat().st_mtime) < max_age_hours * 3600
    if not fresh_enough:
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 404:
                if required:
                    raise FileNotFoundError(url)
                log.warning("not published yet: %s", url)
                return None
            r.raise_for_status()
            dest.write_bytes(r.content)
            lm = r.headers.get("Last-Modified")
            meta[filename] = {
                "url": url,
                "source_updated": parsedate_to_datetime(lm).astimezone(timezone.utc).isoformat() if lm else None,
                "fetched": datetime.now(timezone.utc).isoformat(),
            }
            _save_meta(meta)
        except requests.RequestException as e:  # network failure -> fall back to cache
            if not dest.exists():
                if required:
                    raise
                log.warning("download failed and no cache: %s (%s)", url, e)
                return None
            log.warning("download failed, using cached %s (%s)", filename, e)
    if filename not in meta or not meta[filename].get("source_updated"):
        try:  # cached file without provenance: ask the server when it was last modified
            h = requests.head(url, allow_redirects=True, timeout=30)
            lm = h.headers.get("Last-Modified")
            meta[filename] = {"url": url, "fetched": datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).isoformat(),
                              "source_updated": parsedate_to_datetime(lm).astimezone(timezone.utc).isoformat() if lm else None}
            _save_meta(meta)
        except requests.RequestException:
            pass
    m = meta.get(filename, {"url": url})
    FRESHNESS[filename] = m
    return dest


def schedules() -> pd.DataFrame:
    p = fetch("schedules", "games.csv", max_age_hours=1)
    g = pd.read_csv(p, low_memory=False)
    g = g[g.season >= 1999].copy()
    return g


def pbp(season: int, current: bool) -> pd.DataFrame:
    cols = [
        "game_id", "season", "week", "season_type", "posteam", "defteam", "home_team", "away_team",
        "play_type", "pass", "rush", "rush_attempt", "pass_attempt", "qb_dropback", "qb_scramble", "sack",
        "qb_hit", "interception", "fumble_lost", "epa", "success", "yards_gained", "yardline_100", "down",
        "third_down_converted", "third_down_failed", "fourth_down_converted", "fourth_down_failed",
        "special_teams_play", "touchdown", "pass_touchdown", "rush_touchdown", "td_team", "td_player_id",
        "rusher_player_id", "receiver_player_id", "passer_player_id", "air_yards", "drive", "fixed_drive",
        "fixed_drive_result", "drive_time_of_possession", "run_location", "run_gap", "two_point_attempt",
        "qtr", "game_seconds_remaining", "score_differential", "wp", "play_id", "penalty", "first_down",
        "aborted_play",
    ]
    p = fetch("pbp", f"play_by_play_{season}.parquet", max_age_hours=3 if current else float("inf"))
    df = pd.read_parquet(p, columns=cols)
    return df


def player_week(season: int, current: bool) -> pd.DataFrame | None:
    p = fetch("stats_player", f"stats_player_week_{season}.csv", 3 if current else float("inf"), required=False)
    return None if p is None else pd.read_csv(p, low_memory=False)


def injuries(season: int, current: bool) -> pd.DataFrame | None:
    p = fetch("injuries", f"injuries_{season}.csv", 1 if current else float("inf"), required=False)
    return None if p is None else pd.read_csv(p, low_memory=False)


def snap_counts(season: int, current: bool) -> pd.DataFrame | None:
    p = fetch("snap_counts", f"snap_counts_{season}.csv", 3 if current else float("inf"), required=False)
    return None if p is None else pd.read_csv(p, low_memory=False)


def weekly_roster(season: int, current: bool) -> pd.DataFrame | None:
    p = fetch("weekly_rosters", f"roster_weekly_{season}.csv", 3 if current else float("inf"), required=False)
    return None if p is None else pd.read_csv(p, low_memory=False)


def depth_charts(season: int) -> pd.DataFrame | None:
    p = fetch("depth_charts", f"depth_charts_{season}.csv", 3, required=False)
    if p is None:
        return None
    return pd.read_csv(p, low_memory=False, usecols=["dt", "team", "player_name", "gsis_id", "pos_grp", "pos_abb", "pos_rank"])


def ftn(season: int, current: bool) -> pd.DataFrame | None:
    p = fetch("ftn_charting", f"ftn_charting_{season}.csv", 6 if current else float("inf"), required=False)
    if p is None:
        return None
    return pd.read_csv(p, low_memory=False, usecols=[
        "nflverse_game_id", "nflverse_play_id", "is_play_action", "is_motion", "n_blitzers", "n_pass_rushers",
        "n_defense_box", "is_screen_pass", "is_rpo", "is_qb_out_of_pocket"])


def players() -> pd.DataFrame:
    p = fetch("players", "players.csv", max_age_hours=24)
    return pd.read_csv(p, low_memory=False, usecols=["gsis_id", "display_name", "position", "pfr_id", "headshot",
                                                     "latest_team", "status", "rookie_season"])


def teams() -> pd.DataFrame:
    p = fetch("teams", "teams_colors_logos.csv", max_age_hours=24 * 7)
    return pd.read_csv(p)


def seed_cache_from(dir_: Path, mapping: dict[str, str]) -> None:
    """Dev helper: copy already-downloaded files into the cache."""
    import shutil
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for src, dst in mapping.items():
        s = dir_ / src
        if s.exists() and not (CACHE_DIR / dst).exists():
            shutil.copy(s, CACHE_DIR / dst)
