from datetime import datetime
from typing import Optional

from langchain_community.tools import DuckDuckGoSearchResults, DuckDuckGoSearchRun
from langchain_core.tools import tool

_ddg_results = DuckDuckGoSearchResults(num_results=5)
_ddg_run = DuckDuckGoSearchRun()


def _parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


@tool
def search_hotels(
    location: str,
    check_in: str,
    check_out: str,
    guests: int = 2,
    max_price_per_night: Optional[int] = None,
) -> str:
    """Search for hotels and accommodation at a destination.

    Use this when a traveler asks about where to stay, hotel prices,
    or accommodation options.

    Args:
        location: City or area to stay (e.g., "Amsterdam", "Bali", "Manhattan New York")
        check_in: Check-in date in YYYY-MM-DD format (e.g., "2026-07-01")
        check_out: Check-out date in YYYY-MM-DD format (e.g., "2026-07-08")
        guests: Number of guests (default: 2)
        max_price_per_night: Optional maximum budget per night in USD (e.g., 150)
    """
    dep_dt = _parse_date(check_in)
    ret_dt = _parse_date(check_out)
    year = dep_dt.year if dep_dt else datetime.now().year

    nights = (ret_dt - dep_dt).days if dep_dt and ret_dt else None
    nights_str = f"{nights}-night " if nights else ""
    budget_str = f"under ${max_price_per_night} per night " if max_price_per_night else ""
    guests_str = f"{guests} guest{'s' if guests != 1 else ''} "

    query = (
        f"best hotels {location} {year} {budget_str}"
        f"{nights_str}stay {guests_str}reviews recommended"
    )

    try:
        result = _ddg_results.run(query)
    except Exception:
        result = _ddg_run.run(query)

    stay_str = f"{check_in} to {check_out}" if check_in and check_out else "dates TBD"
    budget_label = f" (budget: {budget_str.strip()})" if budget_str else ""

    return (
        f"Hotel search in {location} — {stay_str}, "
        f"{guests} guest{'s' if guests != 1 else ''}{budget_label}:\n\n"
        f"{result}\n\n"
        f"Tip: Compare prices on Booking.com, Hotels.com, or Airbnb. Book early for best rates."
    )
