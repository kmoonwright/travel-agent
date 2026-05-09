from datetime import datetime

import requests
from langchain_core.tools import tool

from .geo import _geocode

TIMEZONE_URL = "https://timeapi.io/api/timezone/coordinate"
CURRENT_TIME_URL = "https://timeapi.io/api/time/current/zone"


@tool
def get_local_time(location: str) -> str:
    """Get the current local time and timezone at a travel destination.

    Use this when planning calls home, scheduling activities across time zones,
    or checking whether businesses are currently open at the destination.

    Args:
        location: City or country name (e.g., "Tokyo", "London", "New York")
    """
    coords = _geocode(location)
    if coords is None:
        return f"Could not determine location for '{location}'. Try a more specific name."

    lat, lon = coords

    try:
        tz_resp = requests.get(
            TIMEZONE_URL,
            params={"latitude": lat, "longitude": lon},
            timeout=10,
        )
        tz_resp.raise_for_status()
        timezone = tz_resp.json().get("timeZone")
        if not timezone:
            return f"Could not determine timezone for '{location}'."

        time_resp = requests.get(
            CURRENT_TIME_URL,
            params={"timeZone": timezone},
            timeout=10,
        )
        time_resp.raise_for_status()
        t = time_resp.json()

        dt = datetime(t["year"], t["month"], t["day"], t["hour"], t["minute"])
        dst_note = " (DST active)" if t.get("dstActive") else ""

        return (
            f"Local time in {location.title()}:\n"
            f"Current time: {dt.strftime('%A, %B %d, %Y')} at {dt.strftime('%I:%M %p')}\n"
            f"Timezone: {timezone}{dst_note}"
        )

    except requests.exceptions.RequestException as e:
        return f"Time service unavailable: {e}. Please try again."
