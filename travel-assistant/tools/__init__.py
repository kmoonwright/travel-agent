from .advisories import get_travel_advisory
from .attractions import search_attractions
from .climate import get_seasonal_climate
from .currency import convert_currency
from .flights import search_flights
from .geo import geocode_location
from .hotels import search_hotels
from .restaurants import search_restaurants
from .time import get_local_time
from .utils import calculate_trip_duration
from .weather import get_weather

ALL_TOOLS = [
    geocode_location,
    get_weather,
    get_seasonal_climate,
    search_attractions,
    search_restaurants,
    convert_currency,
    search_flights,
    search_hotels,
    get_travel_advisory,
    get_local_time,
    calculate_trip_duration,
]
