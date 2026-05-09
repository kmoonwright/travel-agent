from datetime import datetime

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool

from .models import TravelAdvisoryResult

_ddg = DuckDuckGoSearchRun()


@tool
def get_travel_advisory(country: str) -> TravelAdvisoryResult:
    """Get current travel safety advisory information for a destination country.

    Always call this tool for any destination a traveler mentions, regardless of
    perceived safety level — even low-risk countries have official advisories with
    entry requirements, health notices, and local laws worth knowing.

    Args:
        country: Country name or common abbreviation (e.g., "Mexico", "Thailand", "Japan")
    """
    year = datetime.now().year

    us_query = (
        f"{country} travel advisory {year} US State Department "
        f"safety level exercise normal caution do not travel"
    )
    uk_query = f"{country} FCDO foreign travel advice {year} safety entry requirements"

    return TravelAdvisoryResult(
        country=country.title(),
        us_advisory=_ddg.run(us_query),
        uk_advisory=_ddg.run(uk_query),
    )
