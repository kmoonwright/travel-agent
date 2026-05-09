import requests
from langchain_core.tools import tool

from .models import GeocodeResult

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "travel-assistant/1.0"}


def _geocode(location: str) -> tuple[float, float] | None:
    """Internal helper: returns (lat, lon) or None on failure."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": location, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


@tool
def geocode_location(location: str) -> GeocodeResult:
    """Get geographic coordinates and full details for a place name, city, or address.

    Use this when you need to confirm where a location is, get its coordinates,
    or resolve an ambiguous place name before using other tools.

    Args:
        location: Place name, city, or address (e.g., "Paris", "Rome, Italy", "Times Square New York")
    """
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": location, "format": "json", "limit": 1, "addressdetails": 1},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return GeocodeResult(error=f"Could not find coordinates for '{location}'. Try a more specific name (e.g., add the country).")

        result = data[0]
        lat = float(result["lat"])
        lon = float(result["lon"])
        display_name = result.get("display_name", "")
        country = result.get("address", {}).get("country", "Unknown")

        return GeocodeResult(
            display_name=display_name,
            lat=lat,
            lon=lon,
            country=country,
        )
    except requests.exceptions.RequestException as e:
        return GeocodeResult(error=f"Geocoding service unavailable: {e}")
