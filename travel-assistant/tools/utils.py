from datetime import date, datetime

from langchain_core.tools import tool

from .models import TripDurationResult


@tool
def calculate_trip_duration(departure_date: str, return_date: str) -> TripDurationResult:
    """Calculate the duration of a trip between two dates.

    Use this when a traveler wants to know how long their trip is, plan
    leave from work, or understand the length of their itinerary.

    Args:
        departure_date: Departure date in YYYY-MM-DD format (e.g., "2026-06-01")
        return_date: Return date in YYYY-MM-DD format (e.g., "2026-06-15")
    """
    try:
        dep = datetime.strptime(departure_date, "%Y-%m-%d").date()
        ret = datetime.strptime(return_date, "%Y-%m-%d").date()
    except ValueError:
        return TripDurationResult(error="Invalid date format. Use YYYY-MM-DD (e.g., '2026-06-01').")

    if ret <= dep:
        return TripDurationResult(error=f"Return date ({return_date}) must be after departure date ({departure_date}).")

    today = date.today()
    total_days = (ret - dep).days
    weeks, remainder = divmod(total_days, 7)

    if dep < today:
        note = "Departure date is in the past."
        days_until = None
    elif dep == today:
        note = "Departure is today!"
        days_until = 0
    else:
        days_until = (dep - today).days
        note = f"Departure is {days_until} day{'s' if days_until != 1 else ''} from today."

    return TripDurationResult(
        departure_date=departure_date,
        return_date=return_date,
        total_days=total_days,
        weeks=weeks,
        remainder_days=remainder,
        days_until_departure=days_until,
        note=note,
    )
