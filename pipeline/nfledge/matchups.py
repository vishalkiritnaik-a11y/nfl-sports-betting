"""Measured offense-vs-defense scheme tendencies for the current season.

Sources: nflverse play-by-play (run location/gap, pressure, red zone, target
position) and FTN charting via nflverse (play action, motion, blitzers, box count).
Man/zone and single-high/two-high coverage are NOT in the free data and are
reported as unavailable rather than inferred.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_N = {"default": 25}

METRICS = [
    # key, label, side-specific filter description, higher_is_better_for_offense
    ("pass_epa", "Pass EPA / dropback"),
    ("rush_in_epa", "Inside run EPA (A/B gaps)"),
    ("rush_out_epa", "Outside run EPA (C gap / edge)"),
    ("pa_epa", "Play-action EPA / dropback"),
    ("vs_blitz_epa", "EPA / dropback vs blitz"),
    ("pressure_rate", "Pressure rate (sacks + hits / dropback)"),
    ("heavy_box_rush_epa", "Rush EPA vs 8+ man box"),
    ("explosive_rate", "Explosive play rate"),
    ("rz_td_rate", "Red-zone TD rate (drives)"),
    ("epa_to_wr", "EPA / target to WRs"),
    ("epa_to_te", "EPA / target to TEs"),
    ("epa_to_rb", "EPA / target to RBs"),
]
# For pressure_rate higher is better for the DEFENSE; all others higher favours offense.
DEF_GOOD_HIGH = {"pressure_rate"}


def _agg(df: pd.DataFrame, key: str, team_col: str, mask, val: str = "epa") -> pd.DataFrame:
    x = df[mask].groupby(team_col)[val].agg(["mean", "size"])
    x.columns = [f"{key}", f"{key}_n"]
    return x


def scheme_tables(pbp: pd.DataFrame, ftn: pd.DataFrame | None, positions: dict, before: str, games: pd.DataFrame) -> dict:
    gd = games.set_index("game_id").gameday
    p = pbp[(pbp.game_id.map(gd) < before) & pbp.play_type.isin(["pass", "run"]) & pbp.epa.notna() & (pbp.two_point_attempt != 1)].copy()
    if p.empty:
        return {}
    if ftn is not None and len(ftn):
        f = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
        p = p.merge(f, on=["game_id", "play_id"], how="left")
    else:
        for c in ("is_play_action", "n_blitzers", "n_defense_box"):
            p[c] = np.nan
    db = p.qb_dropback == 1
    ru = (p["rush"] == 1) & (p.qb_scramble != 1)
    inside = ru & ((p.run_location == "middle") | (p.run_gap == "guard"))
    outside = ru & p.run_gap.isin(["tackle", "end"])
    pa = db & (p.is_play_action.astype(str).str.upper() == "TRUE")
    blitz = db & (pd.to_numeric(p.n_blitzers, errors="coerce") > 0)
    heavy = ru & (pd.to_numeric(p.n_defense_box, errors="coerce") >= 8)
    p["press"] = ((p.sack == 1) | (p.qb_hit == 1)).astype(float)
    p["expl"] = (((p["pass"] == 1) & (p.yards_gained >= 20)) | ((p["rush"] == 1) & (p.yards_gained >= 10))).astype(float)
    tgt = (p.pass_attempt == 1) & p.receiver_player_id.notna() & (p.sack != 1)
    p["tpos"] = p.receiver_player_id.map(positions)
    out = {}
    for side, col in (("off", "posteam"), ("def", "defteam")):
        parts = [
            _agg(p, "pass_epa", col, db), _agg(p, "rush_in_epa", col, inside), _agg(p, "rush_out_epa", col, outside),
            _agg(p, "pa_epa", col, pa), _agg(p, "vs_blitz_epa", col, blitz),
            _agg(p, "pressure_rate", col, db, "press"), _agg(p, "heavy_box_rush_epa", col, heavy),
            _agg(p, "explosive_rate", col, p.epa.notna(), "expl"),
            _agg(p, "epa_to_wr", col, tgt & (p.tpos == "WR")), _agg(p, "epa_to_te", col, tgt & (p.tpos == "TE")),
            _agg(p, "epa_to_rb", col, tgt & (p.tpos == "RB")),
        ]
        t = pd.concat(parts, axis=1)
        t["pa_rate"] = p[db].groupby(col).apply(lambda d: (d.is_play_action.astype(str).str.upper() == "TRUE").mean(), include_groups=False)
        t["blitz_rate"] = p[db].groupby(col).apply(lambda d: (pd.to_numeric(d.n_blitzers, errors="coerce") > 0).mean(), include_groups=False)
        # red-zone TD rate by drive
        dr = p[p.fixed_drive.notna()].groupby(["game_id", col, "fixed_drive"]).agg(yl=("yardline_100", "min"), res=("fixed_drive_result", "last"))
        dr = dr[dr.yl <= 20]
        rz = dr.groupby(col).res.agg(lambda s: (s == "Touchdown").mean())
        t["rz_td_rate"] = rz
        t["rz_td_rate_n"] = dr.groupby(col).size()
        for k in t.columns:
            if k.endswith("_n"):
                continue
        out[side] = t
    # league ranks (1 = best for the unit in question)
    res = {}
    teams = sorted(set(out["off"].index) | set(out["def"].index))
    for team in teams:
        res[team] = {"off": {}, "def": {}}
        for side in ("off", "def"):
            t = out[side]
            for key, label in METRICS:
                if key not in t or team not in t.index or pd.isna(t.loc[team, key]):
                    continue
                v = float(t.loc[team, key])
                n = int(t.loc[team, f"{key}_n"]) if f"{key}_n" in t else None
                col = t[key].dropna()
                hib = (key in DEF_GOOD_HIGH) == (side == "def")  # higher is better for this unit?
                rank = int((col > v).sum() + 1) if hib else int((col < v).sum() + 1)
                z = float((v - col.mean()) / col.std()) if col.std() > 0 else 0.0
                res[team][side][key] = {"value": v, "n": n, "rank": rank, "z": z, "label": label}
            for extra in ("pa_rate", "blitz_rate"):
                if extra in t and team in t.index and pd.notna(t.loc[team, extra]):
                    res[team][side][extra] = {"value": float(t.loc[team, extra])}
    return res


def matchup_rows(tables: dict, offense: str, defense: str) -> list[dict]:
    """Offense unit vs opposing defense on each measured dimension."""
    o, d = tables.get(offense, {}).get("off", {}), tables.get(defense, {}).get("def", {})
    rows = []
    for key, label in METRICS:
        if key not in o or key not in d:
            continue
        n_o, n_d = o[key]["n"] or 0, d[key]["n"] or 0
        enough = n_o >= MIN_N["default"] and n_d >= MIN_N["default"]
        # z for offense: higher is better unless pressure; for defense-allowed: higher favours offense unless pressure
        z_off = o[key]["z"] * (-1 if key in DEF_GOOD_HIGH else 1)
        z_def = d[key]["z"] * (-1 if key in DEF_GOOD_HIGH else 1)
        edge = z_off + z_def
        verdict = "insufficient sample" if not enough else ("favours offense" if edge > 1.0 else "favours defense" if edge < -1.0 else "neutral")
        rows.append({"key": key, "label": label, "off_value": o[key]["value"], "off_rank": o[key]["rank"], "off_n": n_o,
                     "def_value": d[key]["value"], "def_rank": d[key]["rank"], "def_n": n_d,
                     "edge_z": round(edge, 2), "verdict": verdict, "kind": "measured"})
    extras = {}
    for k in ("pa_rate", "blitz_rate"):
        if k in o:
            extras[f"off_{k}"] = o[k]["value"]
        if k in d:
            extras[f"def_{k}"] = d[k]["value"]
    return rows, extras
