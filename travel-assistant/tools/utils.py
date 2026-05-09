from datetime import date, datetime

from langchain_core.tools import tool


@tool
def calculate_trip_duration(departure_date: str, return_date: str) -> str:
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
        return "Invalid date format. Use YYYY-MM-DD (e.g., '2026-06-01')."

    if ret <= dep:
        return f"Return date ({return_date}) must be after departure date ({departure_date})."

    today = date.today()
    total_days = (ret - dep).days
    weeks, remainder = divmod(total_days, 7)

    parts = []
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if remainder:
        parts.append(f"{remainder} day{'s' if remainder != 1 else ''}")
    duration_str = " and ".join(parts) if parts else "0 days"

    lines = [
        "Trip Duration:",
        f"Departure: {dep.strftime('%A, %B %d, %Y')}",
        f"Return:    {ret.strftime('%A, %B %d, %Y')}",
        f"Total:     {total_days} days ({duration_str})",
    ]

    if dep < today:
        lines.append("Note: Departure date is in the past.")
    elif dep == today:
        lines.append("Note: Departure is today!")
    else:
        days_until = (dep - today).days
        lines.append(f"Note: Departure is {days_until} day{'s' if days_until != 1 else ''} from today.")

    return "\n".join(lines)
