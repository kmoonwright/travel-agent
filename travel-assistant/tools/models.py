from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TravelToolResult(BaseModel):
    """Base for all travel tool results. Serializes to JSON so the LLM receives structured data."""

    error: Optional[str] = None

    def __str__(self) -> str:
        return self.model_dump_json(indent=2, exclude_none=True)


class GeocodeResult(TravelToolResult):
    display_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    country: Optional[str] = None


class LocalTimeResult(TravelToolResult):
    location: Optional[str] = None
    datetime_str: Optional[str] = None
    day_of_week: Optional[str] = None
    timezone: Optional[str] = None
    dst_active: Optional[bool] = None


class CurrentWeather(BaseModel):
    temperature: Optional[float] = None
    humidity_pct: Optional[int] = None
    wind_speed_kmh: Optional[float] = None
    condition: Optional[str] = None
    units: Optional[str] = None


class DailyForecast(BaseModel):
    date: Optional[str] = None
    condition: Optional[str] = None
    high: Optional[float] = None
    low: Optional[float] = None
    precipitation_mm: Optional[float] = None


class WeatherResult(TravelToolResult):
    city: Optional[str] = None
    units: Optional[str] = None
    current: Optional[CurrentWeather] = None
    forecast: Optional[list[DailyForecast]] = None


class ClimateResult(TravelToolResult):
    city: Optional[str] = None
    month: Optional[str] = None
    units: Optional[str] = None
    avg_high: Optional[float] = None
    avg_low: Optional[float] = None
    max_temp: Optional[float] = None
    min_temp: Optional[float] = None
    total_precip_mm: Optional[float] = None
    rainy_days: Optional[int] = None
    reference_year: Optional[int] = None


class Attraction(BaseModel):
    name: str
    category: str


class AttractionSearchResult(TravelToolResult):
    location: Optional[str] = None
    radius_km: Optional[float] = None
    source: Optional[str] = None
    attractions: Optional[list[Attraction]] = None
    web_results: Optional[str] = None


class Restaurant(BaseModel):
    name: str
    cuisine: Optional[str] = None
    address: Optional[str] = None


class RestaurantSearchResult(TravelToolResult):
    location: Optional[str] = None
    cuisine_filter: Optional[str] = None
    radius_km: Optional[float] = None
    source: Optional[str] = None
    restaurants: Optional[list[Restaurant]] = None
    web_results: Optional[str] = None


class HotelSearchResult(TravelToolResult):
    location: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    guests: Optional[int] = None
    max_price_per_night: Optional[int] = None
    nights: Optional[int] = None
    search_results: Optional[str] = None


class FlightSearchResult(TravelToolResult):
    origin: Optional[str] = None
    destination: Optional[str] = None
    date: Optional[str] = None
    cabin_class: Optional[str] = None
    passengers: Optional[int] = None
    search_results: Optional[str] = None


class CurrencyConversionResult(TravelToolResult):
    amount: Optional[float] = None
    from_currency: Optional[str] = None
    to_currency: Optional[str] = None
    converted: Optional[float] = None
    rate: Optional[float] = None
    rate_updated: Optional[str] = None


class TravelAdvisoryResult(TravelToolResult):
    country: Optional[str] = None
    us_advisory: Optional[str] = None
    uk_advisory: Optional[str] = None


class TripDurationResult(TravelToolResult):
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    total_days: Optional[int] = None
    weeks: Optional[int] = None
    remainder_days: Optional[int] = None
    days_until_departure: Optional[int] = None
    note: Optional[str] = None
