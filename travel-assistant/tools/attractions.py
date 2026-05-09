import requests
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from opentelemetry import trace

from .geo import _geocode

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_ddg = DuckDuckGoSearchRun()


@tool
def search_attractions(location: str, radius_km: float = 5, limit: int = 10) -> str:
    """Find tourist attractions, landmarks, and points of interest at a destination.

    Use this when a traveler asks what to see, do, or visit — museums, historic sites,
    viewpoints, theme parks, galleries, zoos, and more.

    Args:
        location: City or area name (e.g., "Barcelona", "Kyoto, Japan")
        radius_km: Search radius in kilometers from the city center (default: 5)
        limit: Maximum number of results to return (default: 10)
    """
    coords = _geocode(location)
    if coords is None:
        return f"Could not determine location for '{location}'. Try a more specific name."

    lat, lon = coords
    radius_m = radius_km * 1000

    query = f"""
[out:json][timeout:25];
(
  node["tourism"~"attraction|museum|gallery|viewpoint|theme_park|zoo|aquarium|artwork"](around:{radius_m},{lat},{lon});
  node["historic"~"monument|castle|ruins|memorial|archaeological_site"](around:{radius_m},{lat},{lon});
  way["tourism"~"attraction|museum|gallery|viewpoint|theme_park|zoo|aquarium"](around:{radius_m},{lat},{lon});
  way["historic"~"monument|castle|ruins|memorial"](around:{radius_m},{lat},{lon});
);
out body {limit * 3};
"""

    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])

        seen = set()
        attractions = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            category = (tags.get("tourism") or tags.get("historic", "attraction")).replace("_", " ").title()
            attractions.append((name, category))
            if len(attractions) >= limit:
                break

        if attractions:
            lines = [f"Top attractions near {location.title()} (within {radius_km}km):"]
            for i, (name, category) in enumerate(attractions):
                lines.append(f"  {i + 1}. {name} ({category})")
            return "\n".join(lines)

    except requests.exceptions.RequestException as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.set_attribute("tool.fallback", True)

    # Fallback to web search
    result = _ddg.run(f"top tourist attractions things to do in {location}")
    return f"Top things to do in {location.title()} (web search):\n{result}"
