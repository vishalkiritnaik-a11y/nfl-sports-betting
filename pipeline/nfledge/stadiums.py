"""Static stadium reference table (location, timezone, elevation, roof type).

Keyed by nflverse ``stadium_id``. Roof types: outdoor | dome | retractable.
Coordinates are used for travel distance and for weather forecast lookups.
Maintained by hand; add new international venues here when the schedule adds them.
"""
from __future__ import annotations

import math

# id: (name, lat, lon, tz, elevation_m, roof)
STADIUMS: dict[str, tuple[str, float, float, str, int, str]] = {
    "ATL97": ("Mercedes-Benz Stadium", 33.7554, -84.4008, "America/New_York", 320, "retractable"),
    "ATL00": ("Georgia Dome", 33.7577, -84.4008, "America/New_York", 320, "dome"),
    "BAL00": ("M&T Bank Stadium", 39.2780, -76.6227, "America/New_York", 10, "outdoor"),
    "BOS00": ("Gillette Stadium", 42.0909, -71.2643, "America/New_York", 90, "outdoor"),
    "BUF00": ("Highmark Stadium", 42.7738, -78.7870, "America/New_York", 180, "outdoor"),
    "CAR00": ("Bank of America Stadium", 35.2258, -80.8528, "America/New_York", 230, "outdoor"),
    "CHI98": ("Soldier Field", 41.8623, -87.6167, "America/Chicago", 180, "outdoor"),
    "CIN00": ("Paycor Stadium", 39.0955, -84.5161, "America/New_York", 150, "outdoor"),
    "CLE00": ("Huntington Bank Field", 41.5061, -81.6995, "America/New_York", 180, "outdoor"),
    "DAL00": ("AT&T Stadium", 32.7473, -97.0945, "America/Chicago", 180, "retractable"),
    "DEN00": ("Empower Field at Mile High", 39.7439, -105.0201, "America/Denver", 1609, "outdoor"),
    "DET00": ("Ford Field", 42.3400, -83.0456, "America/Detroit", 180, "dome"),
    "GNB00": ("Lambeau Field", 44.5013, -88.0622, "America/Chicago", 200, "outdoor"),
    "HOU00": ("NRG Stadium", 29.6847, -95.4107, "America/Chicago", 15, "retractable"),
    "IND00": ("Lucas Oil Stadium", 39.7601, -86.1639, "America/Indiana/Indianapolis", 220, "retractable"),
    "JAX00": ("EverBank Stadium", 30.3239, -81.6373, "America/New_York", 5, "outdoor"),
    "KAN00": ("GEHA Field at Arrowhead Stadium", 39.0489, -94.4839, "America/Chicago", 270, "outdoor"),
    "LAX01": ("SoFi Stadium", 33.9535, -118.3392, "America/Los_Angeles", 30, "dome"),
    "LAX97": ("Dignity Health Sports Park", 33.8644, -118.2611, "America/Los_Angeles", 10, "outdoor"),
    "LAX99": ("Los Angeles Memorial Coliseum", 34.0141, -118.2879, "America/Los_Angeles", 60, "outdoor"),
    "MIA00": ("Hard Rock Stadium", 25.9580, -80.2389, "America/New_York", 5, "outdoor"),
    "MIN01": ("U.S. Bank Stadium", 44.9737, -93.2577, "America/Chicago", 250, "dome"),
    "NAS00": ("Nissan Stadium", 36.1665, -86.7713, "America/Chicago", 130, "outdoor"),
    "NOR00": ("Caesars Superdome", 29.9511, -90.0812, "America/Chicago", 0, "dome"),
    "NYC01": ("MetLife Stadium", 40.8135, -74.0745, "America/New_York", 5, "outdoor"),
    "OAK00": ("Oakland Coliseum", 37.7516, -122.2005, "America/Los_Angeles", 10, "outdoor"),
    "PHI00": ("Lincoln Financial Field", 39.9008, -75.1675, "America/New_York", 10, "outdoor"),
    "PHO00": ("State Farm Stadium", 33.5276, -112.2626, "America/Phoenix", 330, "retractable"),
    "PIT00": ("Acrisure Stadium", 40.4468, -80.0158, "America/New_York", 220, "outdoor"),
    "SDG00": ("Qualcomm Stadium", 32.7831, -117.1196, "America/Los_Angeles", 30, "outdoor"),
    "SEA00": ("Lumen Field", 47.5952, -122.3316, "America/Los_Angeles", 5, "outdoor"),
    "SFO01": ("Levi's Stadium", 37.4030, -121.9700, "America/Los_Angeles", 5, "outdoor"),
    "TAM00": ("Raymond James Stadium", 27.9759, -82.5033, "America/New_York", 10, "outdoor"),
    "VEG00": ("Allegiant Stadium", 36.0909, -115.1833, "America/Los_Angeles", 610, "dome"),
    "WAS00": ("Northwest Stadium", 38.9076, -76.8645, "America/New_York", 50, "outdoor"),
    # International / neutral venues
    "LON00": ("Wembley Stadium", 51.5560, -0.2795, "Europe/London", 30, "outdoor"),
    "LON01": ("Twickenham Stadium", 51.4560, -0.3415, "Europe/London", 10, "outdoor"),
    "LON02": ("Tottenham Hotspur Stadium", 51.6043, -0.0664, "Europe/London", 30, "outdoor"),
    "MEX00": ("Estadio Banorte", 19.3029, -99.1505, "America/Mexico_City", 2240, "outdoor"),
    "FRA00": ("Deutsche Bank Park", 50.0686, 8.6455, "Europe/Berlin", 110, "outdoor"),
    "GER00": ("Allianz Arena", 48.2188, 11.6247, "Europe/Berlin", 520, "outdoor"),
    "MUN01": ("Allianz Arena", 48.2188, 11.6247, "Europe/Berlin", 520, "outdoor"),
    "MAD01": ("Santiago Bernabeu", 40.4531, -3.6883, "Europe/Madrid", 660, "retractable"),
    "PAR00": ("Stade de France", 48.9245, 2.3602, "Europe/Paris", 40, "outdoor"),
    "MEL00": ("Melbourne Cricket Ground", -37.8200, 144.9834, "Australia/Melbourne", 30, "outdoor"),
    "RIO00": ("Maracana Stadium", -22.9122, -43.2302, "America/Sao_Paulo", 10, "outdoor"),
    "SAO00": ("Neo Quimica Arena", -23.5453, -46.4742, "America/Sao_Paulo", 760, "outdoor"),
}

# Fallback team home venue (used when a team has no home game yet in a season)
TEAM_HOME = {
    "ARI": "PHO00", "ATL": "ATL97", "BAL": "BAL00", "BUF": "BUF00", "CAR": "CAR00", "CHI": "CHI98",
    "CIN": "CIN00", "CLE": "CLE00", "DAL": "DAL00", "DEN": "DEN00", "DET": "DET00", "GB": "GNB00",
    "HOU": "HOU00", "IND": "IND00", "JAX": "JAX00", "KC": "KAN00", "LA": "LAX01", "LAC": "LAX01",
    "LV": "VEG00", "MIA": "MIA00", "MIN": "MIN01", "NE": "BOS00", "NO": "NOR00", "NYG": "NYC01",
    "NYJ": "NYC01", "PHI": "PHI00", "PIT": "PIT00", "SEA": "SEA00", "SF": "SFO01", "TB": "TAM00",
    "TEN": "NAS00", "WAS": "WAS00", "OAK": "OAK00", "SD": "SDG00", "STL": "LAX99",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_ALIASES = {"tottenham": "LON02", "wembley": "LON00", "twickenham": "LON01", "azteca": "MEX00", "banorte": "MEX00",
            "allianz": "MUN01", "deutsche bank park": "FRA00", "frankfurt": "FRA00", "bernabeu": "MAD01",
            "stade de france": "PAR00", "melbourne": "MEL00", "maracana": "RIO00", "corinthians": "SAO00",
            "neo quimica": "SAO00"}


def resolve(stadium_id: str | None, stadium_name: str | None = None) -> str | None:
    """nflverse sometimes keeps the home team's stadium_id for international
    'home' games (e.g. JAX in London); the stadium name is authoritative there."""
    if isinstance(stadium_name, str):
        low = stadium_name.lower()
        for k, v in _ALIASES.items():
            if k in low:
                return v
    return stadium_id


def info(stadium_id: str | None, stadium_name: str | None = None) -> dict | None:
    stadium_id = resolve(stadium_id, stadium_name)
    if not stadium_id or stadium_id not in STADIUMS:
        return None
    n, lat, lon, tz, elev, roof = STADIUMS[stadium_id]
    return {"id": stadium_id, "name": n, "lat": lat, "lon": lon, "tz": tz, "elevation_m": elev, "roof_type": roof}
