import requests
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from opentelemetry import trace

from .geo import _geocode

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_ddg = DuckDuckGoSearchRun()


@tool
def search_restaurants(
    location: str,
    cuisine: str = "",
    radius_km: float = 1,
    limit: int = 10,
) -> str:
    """Find restaurants and cafes near a travel destination with optional cuisine filter.

    Use this when a traveler asks where to eat, wants cuisine-specific recommendations,
    or needs dining options near their hotel or attraction.

    Args:
        location: City or neighborhood name (e.g., "Florence", "Shibuya Tokyo")
        cuisine: Optional cuisine type (e.g., "italian", "sushi", "indian", "vegan", "seafood")
        radius_km: Search radius in kilometers (default: 1 — good for walkable city centers)
        limit: Maximum number of results (default: 10)
    """
    coords = _geocode(location)
    if coords is None:
        return f"Could not determine location for '{location}'. Try a more specific name."

    lat, lon = coords
    radius_m = radius_km * 1000
    cuisine_filter = f'["cuisine"="{cuisine}"]' if cuisine else ""

    query = f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"{cuisine_filter}](around:{radius_m},{lat},{lon});
  node["amenity"="cafe"{cuisine_filter}](around:{radius_m},{lat},{lon});
);
out body {limit * 3};
"""

    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])

        seen = set()
        restaurants = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            cuis = tags.get("cuisine", "").replace(";", ", ")
            street = tags.get("addr:street", "")
            num = tags.get("addr:housenumber", "")
            address = f"{street} {num}".strip()
            restaurants.append((name, cuis, address))
            if len(restaurants) >= limit:
                break

        if restaurants:
            cuisine_label = f" ({cuisine})" if cuisine else ""
            lines = [f"Restaurants near {location.title()}{cuisine_label} (within {radius_km}km):"]
            for i, (name, cuis, addr) in enumerate(restaurants):
                parts = [f"  {i + 1}. {name}"]
                if cuis:
                    parts.append(f"({cuis} cuisine)")
                if addr:
                    parts.append(f"— {addr}")
                lines.append(" ".join(parts))
            return "\n".join(lines)

    except requests.exceptions.RequestException as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.set_attribute("tool.fallback", True)

    # Fallback to web search
    query_str = f"best {cuisine + ' ' if cuisine else ''}restaurants in {location}"
    result = _ddg.run(query_str)
    return f"Restaurants in {location.title()} (web search):\n{result}"
