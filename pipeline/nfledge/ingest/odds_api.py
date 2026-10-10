"""Optional live odds from The Odds API (https://the-odds-api.com).

Disabled unless ODDS_API_KEY is set (GitHub Actions secret). Without it the
dashboard uses the consensus lines that nflverse publishes in its schedule file
(moneyline, spread, total with prices), clearly labelled as such, and the anytime
touchdown market is shown as unavailable.

Free tier: 500 credits/month -> h2h,spreads,totals for the NFL costs 3 credits per
region per call. Anytime-TD props (`player_anytime_td`) are an event-level market
that costs 1 credit per event per market and require a paid plan for volume.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from ..config import ODDS_API_KEY, ODDS_API_REGIONS, ODDS_API_TD_PROPS

log = logging.getLogger(__name__)
BASE = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"

# The Odds API full team names -> nflverse abbreviations
NAME_TO_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}


def enabled() -> bool:
    return bool(ODDS_API_KEY)


def game_odds() -> dict:
    """Return {(away, home): {"books": {book: {...}}, "snapshot": iso}} or {} if disabled/failing."""
    if not enabled():
        return {}
    try:
        r = requests.get(f"{BASE}/odds", params={
            "apiKey": ODDS_API_KEY, "regions": ODDS_API_REGIONS, "markets": "h2h,spreads,totals",
            "oddsFormat": "american"}, timeout=30)
        r.raise_for_status()
        log.info("odds api credits remaining: %s", r.headers.get("x-requests-remaining"))
        events = r.json()
    except Exception as e:
        log.warning("odds api failed: %s", e)
        return {"_error": str(e)[:200]}
    snap = datetime.now(timezone.utc).isoformat()
    out: dict = {}
    for ev in events:
        away, home = NAME_TO_ABBR.get(ev["away_team"]), NAME_TO_ABBR.get(ev["home_team"])
        if not away or not home:
            continue
        books = {}
        for b in ev.get("bookmakers", []):
            row = {"last_update": b.get("last_update")}
            for m in b.get("markets", []):
                for oc in m["outcomes"]:
                    side = "home" if oc["name"] == ev["home_team"] else "away" if oc["name"] == ev["away_team"] else oc["name"].lower()
                    if m["key"] == "h2h":
                        row[f"ml_{side}"] = oc["price"]
                    elif m["key"] == "spreads":
                        row[f"spread_{side}"] = oc.get("point")
                        row[f"spread_{side}_price"] = oc["price"]
                    elif m["key"] == "totals":
                        row[f"total_{side}"] = oc.get("point")
                        row[f"total_{side}_price"] = oc["price"]
            books[b["title"]] = row
        out[(away, home)] = {"event_id": ev["id"], "books": books, "snapshot": snap}
    if ODDS_API_TD_PROPS:
        for key, ev in out.items():
            ev["anytime_td"] = _td_props(ev["event_id"])
    return out


def _td_props(event_id: str) -> dict:
    """{player_name: {book: american_price}} for the anytime-TD market."""
    try:
        r = requests.get(f"{BASE}/events/{event_id}/odds", params={
            "apiKey": ODDS_API_KEY, "regions": ODDS_API_REGIONS, "markets": "player_anytime_td",
            "oddsFormat": "american"}, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.warning("td props failed for %s: %s", event_id, e)
        return {}
    out: dict = {}
    for b in r.json().get("bookmakers", []):
        for m in b.get("markets", []):
            for oc in m["outcomes"]:
                if oc.get("name") == "Yes" or "description" in oc:
                    player = oc.get("description") or oc.get("name")
                    out.setdefault(player, {})[b["title"]] = oc["price"]
    return out
