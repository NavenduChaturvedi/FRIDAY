"""Current weather + today's range for a city. Open-Meteo, no API key."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

TOOL = {
    "name": "get_weather",
    "description": (
        "Current weather and today's high/low for a city. Use for 'what's the "
        "weather', 'is it going to rain', 'how cold is it in Oslo'. Give the "
        "city name; pass the user's own city from memory if they don't say one."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name, e.g. 'Berlin'."},
        },
        "required": ["city"],
    },
}

_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "friday-assistant"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def run(city: str = "") -> str:
    city = (city or "").strip()
    if not city:
        return "Which city?"

    try:
        geo = _get(
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": city, "count": 1})
        )
        results = geo.get("results") or []
        if not results:
            return f"I couldn't find a place called {city!r}."
        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        label = ", ".join(
            x for x in (loc.get("name"), loc.get("country")) if x
        )

        wx = _get(
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 1,
                }
            )
        )
    except Exception as exc:  # noqa: BLE001 — network / parse
        return f"The weather lookup failed: {exc}"

    cur = wx.get("current", {})
    daily = wx.get("daily", {})
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    desc = _WMO.get(cur.get("weather_code"), "unclear conditions")
    hi = (daily.get("temperature_2m_max") or [None])[0]
    lo = (daily.get("temperature_2m_min") or [None])[0]
    rain = (daily.get("precipitation_probability_max") or [None])[0]

    parts = [f"In {label} it's {round(temp)} degrees and {desc}"]
    if feels is not None and abs(feels - temp) >= 3:
        parts.append(f"feels like {round(feels)}")
    if hi is not None and lo is not None:
        parts.append(f"today {round(lo)} to {round(hi)}")
    if rain is not None and rain >= 30:
        parts.append(f"{rain}% chance of rain")
    return ", ".join(parts) + "."
