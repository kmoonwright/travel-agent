import calendar
from datetime import datetime

import requests
from langchain_core.tools import tool

from .geo import _geocode

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def _parse_month(month: str) -> int | None:
    try:
        n = int(month)
        return n if 1 <= n <= 12 else None
    except ValueError:
        return MONTH_NAMES.get(month.lower().strip())


@tool
def get_seasonal_climate(city: str, month: str, units: str = "celsius") -> str:
    """Get typical seasonal weather conditions for a travel destination in a specific month.

    Use this for trip planning when the travel date is more than 7-10 days away —
    it returns historical averages (average highs/lows, rainfall, rainy days) based on
    the previous year's data, giving a realistic picture of what to expect.

    Use get_weather instead for current conditions or trips within the next week.

    Args:
        city: City name, optionally with country (e.g., "Tokyo", "Bangkok, Thailand")
        month: Month name or number (e.g., "July", "7", "Dec", "12")
        units: Temperature units — "celsius" or "fahrenheit" (default: "celsius")
    """
    month_num = _parse_month(month)
    if month_num is None:
        return f"Could not parse month '{month}'. Use a month name (e.g., 'July') or number (e.g., '7')."

    coords = _geocode(city)
    if coords is None:
        return f"Could not determine location for '{city}'. Try adding the country name."

    lat, lon = coords
    use_fahrenheit = units.lower() == "fahrenheit"
    unit_sym = "°F" if use_fahrenheit else "°C"

    now = datetime.now()
    # Always use last year to ensure archive data is fully available
    reference_year = now.year - 1

    last_day = calendar.monthrange(reference_year, month_num)[1]
    start_date = f"{reference_year}-{month_num:02d}-01"
    end_date = f"{reference_year}-{month_num:02d}-{last_day:02d}"
    month_name = datetime(reference_year, month_num, 1).strftime("%B")

    try:
        resp = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto",
                "temperature_unit": "fahrenheit" if use_fahrenheit else "celsius",
            },
            timeout=15,
        )
        resp.raise_for_status()
        daily = resp.json().get("daily", {})

        highs = [v for v in daily.get("temperature_2m_max", []) if v is not None]
        lows = [v for v in daily.get("temperature_2m_min", []) if v is not None]
        precip = [v for v in daily.get("precipitation_sum", []) if v is not None]

        if not highs:
            return f"No historical climate data available for '{city}' in {month_name}."

        avg_high = sum(highs) / len(highs)
        avg_low = sum(lows) / len(lows)
        max_temp = max(highs)
        min_temp = min(lows)
        total_precip = sum(precip)
        rainy_days = sum(1 for p in precip if p > 1.0)

        return (
            f"Typical {month_name} weather in {city.title()} (based on {reference_year} data):\n"
            f"Average High: {avg_high:.1f}{unit_sym}  |  Average Low: {avg_low:.1f}{unit_sym}\n"
            f"Hottest day: {max_temp:.1f}{unit_sym}  |  Coolest day: {min_temp:.1f}{unit_sym}\n"
            f"Total Precipitation: {total_precip:.0f}mm across {rainy_days} rainy day{'s' if rainy_days != 1 else ''}\n"
            f"\nNote: Based on historical data for {month_name} {reference_year}. "
            f"Actual conditions may vary."
        )

    except requests.exceptions.RequestException as e:
        return f"Climate data service unavailable: {e}. Please try again."
