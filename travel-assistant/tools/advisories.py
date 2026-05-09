from datetime import datetime

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool

_ddg = DuckDuckGoSearchRun()


@tool
def get_travel_advisory(country: str) -> str:
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

    us_result = _ddg.run(us_query)
    uk_result = _ddg.run(uk_query)

    return (
        f"Travel advisory information for {country.title()}:\n\n"
        f"US State Department:\n{us_result}\n\n"
        f"UK FCDO:\n{uk_result}\n\n"
        f"Always verify current advisories directly at:\n"
        f"  • US citizens: travel.state.gov\n"
        f"  • UK citizens: gov.uk/foreign-travel-advice\n"
        f"  • Other nationalities: check your country's foreign ministry website"
    )
