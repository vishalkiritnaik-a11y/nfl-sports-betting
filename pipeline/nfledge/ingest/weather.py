"""Game-time weather forecasts from Open-Meteo (free, no key, CC-BY 4.0).

Deterministic forecast: https://api.open-meteo.com/v1/forecast
Ensemble spread (uncertainty): https://ensemble-api.open-meteo.com/v1/ensemble (GFS 31-member)

Only outdoor and retractable-roof venues are queried. For retractable roofs the
forecast is shown but roof status is reported as "not confirmed" until nflverse
records it after the game; a forecast is never presented as a game-day observation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from statistics import quantiles
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
HOURLY = "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,snowfall,wind_speed_10m,wind_gusts_10m,weather_code"


def kickoff_utc(gameday: str, gametime: str) -> datetime:
    """nflverse kickoff times are US/Eastern."""
    t = gametime if isinstance(gametime, str) and ":" in gametime else "13:00"
    local = datetime.strptime(f"{gameday} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    return local.astimezone(timezone.utc)


def _nearest(times: list[str], target: datetime) -> int:
    best, bi = None, 0
    for i, s in enumerate(times):
        d = abs((datetime.fromisoformat(s).replace(tzinfo=timezone.utc) - target).total_seconds())
        if best is None or d < best:
            best, bi = d, i
    return bi


def forecast(lat: float, lon: float, ko: datetime, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    lead_h = (ko - now).total_seconds() / 3600
    if lead_h > 16 * 24:
        return {"status": "beyond_forecast_range", "lead_hours": round(lead_h)}
    if lead_h < -4:
        return None
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "hourly": HOURLY, "timezone": "UTC",
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch",
            "start_date": (ko - timedelta(hours=3)).date().isoformat(),
            "end_date": (ko + timedelta(hours=4)).date().isoformat(),
        }, timeout=30)
        r.raise_for_status()
        h = r.json()["hourly"]
    except Exception as e:  # network / API failure: report unavailable, never guess
        log.warning("weather unavailable: %s", e)
        return {"status": "unavailable", "error": str(e)[:120]}
    i = _nearest(h["time"], ko)
    win = range(max(0, i), min(len(h["time"]), i + 4))  # kickoff + ~3h game window
    out = {
        "status": "forecast",
        "source": "Open-Meteo",
        "lead_hours": round(lead_h, 1),
        "temp_f": h["temperature_2m"][i],
        "humidity_pct": h["relative_humidity_2m"][i],
        "wind_mph": max(h["wind_speed_10m"][j] for j in win),
        "gust_mph": max(h["wind_gusts_10m"][j] for j in win),
        "precip_prob_pct": max((h["precipitation_probability"][j] or 0) for j in win),
        "precip_in": round(sum((h["precipitation"][j] or 0) for j in win), 2),
        "snow_in": round(sum((h["snowfall"][j] or 0) for j in win), 2),
        "weather_code": h["weather_code"][i],
        "fetched": now.isoformat(),
    }
    out.update(_ensemble(lat, lon, ko))
    return out


def _ensemble(lat: float, lon: float, ko: datetime) -> dict:
    """10th-90th percentile range for wind and temperature across GFS members."""
    try:
        r = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m,wind_speed_10m", "models": "gfs_seamless",
            "timezone": "UTC", "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
            "start_date": ko.date().isoformat(), "end_date": (ko + timedelta(hours=4)).date().isoformat(),
        }, timeout=30)
        r.raise_for_status()
        h = r.json()["hourly"]
        i = _nearest(h["time"], ko)
        winds = [v[i] for k, v in h.items() if k.startswith("wind_speed_10m") and v[i] is not None]
        temps = [v[i] for k, v in h.items() if k.startswith("temperature_2m") and v[i] is not None]
        if len(winds) < 5:
            return {}
        qw, qt = quantiles(winds, n=10), quantiles(temps, n=10)
        return {"wind_range_mph": [round(qw[0], 1), round(qw[-1], 1)], "temp_range_f": [round(qt[0]), round(qt[-1])],
                "ensemble_members": len(winds)}
    except Exception as e:
        log.info("ensemble unavailable: %s", e)
        return {}
