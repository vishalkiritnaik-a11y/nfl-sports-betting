"""One recommendation per market (spread, moneyline, total) for each game.

Each side gets a 1-10 score built from five plainly stated inputs, starting at 5:

  stats model   model probability vs the no-vig market, +/-0.5 max (edge_pp / 10). Out of sample the
                model has not beaten closing lines, so on its own it can't even make a Lean.
  proven angle  a pattern that beat closing lines on games it was NOT discovered on (see wind_under_record):
                forecast kickoff wind >= 12 mph at an open-air stadium -> Under +2 / Over -2. Re-measured
                every build; halved when the last 3 seasons fall below break-even, zero if the long-run edge goes.
  line move     the line moved toward this side since it opened: +1 / -1
  price         market-anchored EV at the current price worse than -5c (more than the usual vig): -1
  experts       net picks from professional handicappers / betting models in the notes file, +/-1 max (needs 2+ picks)
  news          explicit, sourced adjustments in the notes file (injuries etc.), +/-1.5 max

The pick is the higher-scoring side. Verdict: 7+ Bet, 6 Lean, 5 or less Pass.
A Bet needs a proven angle, or line movement plus sourced news/expert agreement.

Notes live in data/notes/<game_id>.json and are written from published reporting, with a URL per item.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import odds as O

MARKETS = ("spread", "moneyline", "total")
WIND_MIN = 12.0
ANGLES: dict = {}       # filled once per build by set_angles()


def wind_under_record(games, since: int = 2015, min_wind: float = WIND_MIN) -> dict:
    """Unders in outdoor games with >= min_wind mph at kickoff, against the closing total.
    The pattern was found on 1999-2014; `since` keeps the measurement on games after that."""
    import pandas as pd
    g = games[games.home_score.notna() & games.total_line.notna() & games.wind.notna()
              & ~games.roof.isin(["dome", "closed"]) & (games.wind >= min_wind) & (games.season >= since)]
    tot = g.home_score + g.away_score
    g = g[tot != g.total_line]
    tot = g.home_score + g.away_score
    won = (tot < g.total_line)
    rate = float(won.mean()) if len(g) else 0.0
    recent = won[g.season >= g.season.max() - 2]
    pts = 2.0 if rate >= 0.55 and len(g) >= 200 else 1.0 if rate >= 0.535 and len(g) >= 200 else 0.0
    if len(recent) >= 60 and recent.mean() < 0.524:     # fading lately (below the -110 break-even): halve it
        pts /= 2
    return {"n": int(len(g)), "win_rate": rate, "roi_at_110": rate * (1 + 100 / 110) - 1, "since": since,
            "recent_n": int(len(recent)), "recent_rate": float(recent.mean()) if len(recent) else None,
            "min_wind": min_wind, "points": pts}


def set_angles(games) -> dict:
    ANGLES.clear()
    ANGLES["wind_under"] = wind_under_record(games)
    return dict(ANGLES)


def load_notes(notes_dir: Path, game_id: str) -> dict | None:
    p = notes_dir / f"{game_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def first_logged(con, game_id: str) -> dict | None:
    r = con.execute("SELECT run_id, home_ml, away_ml, spread_line, total_line FROM game_predictions "
                    "WHERE game_id=? AND run_id < kickoff_utc ORDER BY run_id LIMIT 1", (game_id,)).fetchone()
    if not r:
        return None
    return {"source": f"first line logged by this dashboard ({r[0][:10]})", "home_ml": r[1], "away_ml": r[2],
            "spread_line": r[3], "total_line": r[4]}


def _nv_home(hm, am):
    if hm is None or am is None:
        return None
    return O.remove_vig_proportional([O.american_to_implied(hm), O.american_to_implied(am)])[0]


def _fmt(x):
    return f"{x:+g}"


def _side_key(v: dict) -> str:
    return v["team"] or ("over" if v["selection"].startswith("Over") else "under")


def recommend(rec: dict, opening: dict | None, notes: dict | None) -> dict:
    mkt = rec.get("market") or {}
    H, A = rec["home"]["team"], rec["away"]["team"]
    vals = {(v["market"], _side_key(v)): v for v in rec.get("values", [])}
    notes = notes or {}
    out = {}
    for mk in MARKETS:
        sides = [k[1] for k in vals if k[0] == mk]
        if len(sides) != 2:
            continue
        scored = []
        for s in sides:
            v = vals[(mk, s)]
            parts = []   # (label, points, text)
            raw = (v["model_p"] - v["no_vig"]) * 100
            mp = max(-0.5, min(0.5, raw / 10))
            parts.append(("Stats model", mp, f"Model gives {v['model_p']*100:.0f}% vs the market's {v['no_vig']*100:.0f}% (no-vig). Counts little: it hasn't beaten closing lines out of sample"))
            # proven angle: wind unders
            wx = rec.get("weather") or {}
            wa = ANGLES.get("wind_under")
            wind = wx.get("wind_kickoff_mph", wx.get("wind_mph"))
            if mk == "total" and wa and wa["points"] and wx.get("status") == "forecast" and wx.get("roof_type", "outdoor") == "outdoor" and wind is not None and wind >= wa["min_wind"]:
                pts = wa["points"] if s == "under" else -wa["points"]
                parts.append(("Proven angle", pts,
                              f"Forecast wind {wind:.0f} mph at kickoff. Since {wa['since']}, outdoor games with {wa['min_wind']:.0f}+ mph wind went "
                              f"under the closing total {wa['win_rate']*100:.1f}% of the time ({wa['n']} games, {wa['roi_at_110']*100:+.0f}% return at -110; "
                              f"last 3 seasons {wa['recent_rate']*100:.0f}% of {wa['recent_n']})"))
            # line movement
            if opening:
                mv, txt = 0.0, None
                if mk == "spread" and opening.get("spread_line") is not None and mkt.get("spread_line") is not None:
                    d = mkt["spread_line"] - opening["spread_line"]          # + means money on the home side
                    d = d if s == H else -d
                    if abs(d) >= 0.5:
                        mv = 1.0 if d > 0 else -1.0
                        mvd = abs(mkt['spread_line'] - opening['spread_line'])
                        txt = f"Spread moved {mvd:g} pt{'s' if mvd != 1 else ''} {'toward' if d > 0 else 'against'} {s} since open"
                elif mk == "moneyline":
                    o, n = _nv_home(opening.get("home_ml"), opening.get("away_ml")), mkt.get("home_no_vig")
                    if o is not None and n is not None:
                        d = (n - o) if s == H else (o - n)
                        if abs(d) >= 0.02:
                            mv = 1.0 if d > 0 else -1.0
                            txt = f"Moneyline moved {abs(n-o)*100:.0f} pts of win probability {'toward' if d > 0 else 'against'} {s} since open"
                elif mk == "total" and opening.get("total_line") is not None and mkt.get("total_line") is not None:
                    d = mkt["total_line"] - opening["total_line"]
                    d = d if s == "over" else -d
                    if abs(d) >= 0.5:
                        mv = 1.0 if d > 0 else -1.0
                        txt = f"Total moved {opening['total_line']:g} → {mkt['total_line']:g} ({'toward' if d > 0 else 'against'} the {s})"
                if txt:
                    parts.append(("Line move", mv, txt + " (professional money tends to move lines)"))
            # price
            ev = v["ev_per_unit"]
            pp = 0.0 if ev >= -0.05 else -1.0
            parts.append(("Price", pp, f"At {v['odds']:+.0f}, market-anchored EV is {ev*100:+.1f}¢ per $1"))
            # experts
            ex = [e for e in notes.get("experts", []) if e.get("market") == mk]
            if len(ex) >= 2:          # a single published pick is shown but not scored
                net = sum(1 if e["side"] == s else -1 for e in ex)
                xp = max(-1.0, min(1.0, 0.5 * net))
                agree = [e["source"] for e in ex if e["side"] == s]
                parts.append(("Experts", xp, f"{len(agree)} of {len(ex)} published picks on this side" + (f" ({', '.join(agree)})" if agree else "")))
            # news
            npts, ntxt = 0.0, []
            for a in notes.get("adjust", []):
                if a.get("market") not in (mk, "all"):
                    continue
                sign = 1 if a["side"] == s else -1 if a["side"] in sides or a["side"] in (H, A) else 0
                if mk == "total" and a["side"] in (H, A):
                    sign = 0
                if sign:
                    npts += sign * a["points"]
                    ntxt.append(a["reason"])
            if ntxt:
                npts = max(-1.5, min(1.5, npts))
                parts.append(("News", npts, "; ".join(ntxt)))
            total = sum(p[1] for p in parts)
            scored.append((total, v["ev_per_unit"], s, v, parts))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        tot, _, s, v, parts = scored[0]
        score = int(max(1, min(10, math.floor(5 + tot + 1e-9))))
        verdict = "Bet" if score >= 7 else "Lean" if score == 6 else "Pass"
        line = None
        if mk == "spread":
            line = -mkt["spread_line"] if s == H else mkt["spread_line"]
        elif mk == "total":
            line = mkt["total_line"]
        label = (f"{s} ML" if mk == "moneyline" else f"{s} {_fmt(line)}" if mk == "spread"
                 else f"{'Over' if s == 'over' else 'Under'} {line:g}")
        out[mk] = {"market": mk, "side": s, "label": label, "line": line, "odds": v["odds"], "score": score,
                   "verdict": verdict, "p_model": v["model_p"], "p_market": v["no_vig"], "p_win": v.get("anchored_p", v["no_vig"]),
                   "ev": v["ev_per_unit"], "other_score": int(max(1, min(10, math.floor(5 + scored[1][0] + 1e-9)))),
                   "why": [{"factor": p[0], "points": round(p[1], 2), "text": p[2]} for p in parts]}
    return {"markets": out, "opening": opening,
            "notes": {k: notes.get(k) for k in ("updated", "items", "experts") if notes.get(k)} or None}
