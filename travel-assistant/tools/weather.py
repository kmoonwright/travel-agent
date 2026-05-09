from datetime import datetime

import requests
from langchain_core.tools import tool

from .geo import _geocode
from .models import CurrentWeather, DailyForecast, WeatherResult

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


@tool
def get_weather(city: str, units: str = "celsius") -> WeatherResult:
    """Get current weather conditions and 7-day forecast for a travel destination.

    Use this when a traveler wants to know what to pack, whether to expect rain,
    or plan outdoor activities around the weather.

    Args:
        city: City name, optionally with country (e.g., "Bangkok", "Vienna, Austria")
        units: Temperature units — "celsius" or "fahrenheit" (default: "celsius")
    """
    coords = _geocode(city)
    if coords is None:
        return WeatherResult(error=f"Could not determine location for '{city}'. Try adding the country name.")

    lat, lon = coords
    use_fahrenheit = units.lower() == "fahrenheit"
    unit_param = "fahrenheit" if use_fahrenheit else "celsius"
    unit_sym = "°F" if use_fahrenheit else "°C"

    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m,weather_code,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                "forecast_days": 7,
                "timezone": "auto",
                "temperature_unit": unit_param,
                "wind_speed_unit": "kmh",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        cur = data.get("current", {})
        daily = data.get("daily", {})

        current = CurrentWeather(
            temperature=cur.get("temperature_2m"),
            humidity_pct=cur.get("relative_humidity_2m"),
            wind_speed_kmh=cur.get("wind_speed_10m"),
            condition=WMO_CODES.get(cur.get("weather_code", 0), "Unknown"),
            units=unit_sym,
        )

        forecast = []
        dates = daily.get("time", [])
        for i, date_str in enumerate(dates):
            forecast.append(DailyForecast(
                date=date_str,
                condition=WMO_CODES.get(daily.get("weather_code", [0] * 7)[i], "Unknown"),
                high=daily.get("temperature_2m_max", [None] * 7)[i],
                low=daily.get("temperature_2m_min", [None] * 7)[i],
                precipitation_mm=daily.get("precipitation_sum", [0] * 7)[i] or 0,
            ))

        return WeatherResult(city=city.title(), units=unit_sym, current=current, forecast=forecast)

    except requests.exceptions.RequestException as e:
        return WeatherResult(error=f"Weather service unavailable: {e}. Please try again.")
