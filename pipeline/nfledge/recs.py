"""One recommendation per market (spread, moneyline, total) for each game.

Each side gets a 1-10 score built from five plainly stated inputs, starting at 5:

  stats model   model probability vs the no-vig market, +/-1 max (edge_pp / 5)
  line move     the line moved toward this side since it opened: +1 / -1
  price         market-anchored EV at the current price worse than -5c (more than the usual vig): -1
  experts       net picks from professional handicappers / betting models in the notes file, +/-1 max (needs 2+ picks)
  news          explicit, sourced adjustments in the notes file (injuries etc.), +/-1.5 max

The pick is the higher-scoring side. Verdict: 7+ Bet, 6 Lean, 5 or less Pass.
Backtests showed the game model alone has not beaten closing lines, so it is capped at +/-1:
the model by itself can reach Lean, and a Bet needs at least one independent signal agreeing.

Notes live in data/notes/<game_id>.json and are written from published reporting, with a URL per item.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import odds as O

MARKETS = ("spread", "moneyline", "total")


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
            mp = max(-1.0, min(1.0, raw / 5))
            parts.append(("Stats model", mp, f"Model gives {v['model_p']*100:.0f}% vs the market's {v['no_vig']*100:.0f}% (no-vig)"))
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
