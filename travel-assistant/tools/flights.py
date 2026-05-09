from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool

_ddg = DuckDuckGoSearchRun()


@tool
def search_flights(
    origin: str,
    destination: str,
    date: str,
    passengers: int = 1,
    cabin_class: str = "economy",
) -> str:
    """Search for available flights between two destinations.

    Use this when a traveler asks about flights, airfare prices, airlines,
    or schedules between cities or airports.

    Args:
        origin: Departure city or airport code (e.g., "New York", "JFK", "London Heathrow")
        destination: Arrival city or airport code (e.g., "Paris", "CDG", "Tokyo")
        date: Travel date — YYYY-MM-DD or natural language (e.g., "2026-06-15", "next Friday")
        passengers: Number of passengers (default: 1)
        cabin_class: "economy", "premium economy", "business", or "first" (default: "economy")
    """
    query = (
        f"flights from {origin} to {destination} on {date} "
        f"{cabin_class} class {passengers} passenger price airlines schedule"
    )
    result = _ddg.run(query)

    return (
        f"Flight search: {origin} → {destination} on {date} "
        f"({cabin_class}, {passengers} passenger{'s' if passengers != 1 else ''}):\n\n"
        f"{result}\n\n"
        f"Tip: Compare and book on Google Flights, Kayak, Skyscanner, or directly on airline websites."
    )
