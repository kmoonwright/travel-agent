"""
Tests for travel tool structured output and pure-Python logic.

Run with: poetry run pytest tests/
"""

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "travel-assistant"))

from tools.models import (
    ClimateResult,
    CurrencyConversionResult,
    GeocodeResult,
    TravelToolResult,
    TripDurationResult,
    WeatherResult,
)
from tools.utils import calculate_trip_duration
from tools.currency import convert_currency


# ---------------------------------------------------------------------------
# TravelToolResult base model
# ---------------------------------------------------------------------------

class TestTravelToolResult:
    def test_str_is_valid_json(self):
        result = CurrencyConversionResult(
            amount=100.0,
            from_currency="USD",
            to_currency="EUR",
            converted=84.92,
            rate=0.8492,
            rate_updated="2026-05-09",
        )
        parsed = json.loads(str(result))
        assert parsed["amount"] == 100.0
        assert parsed["converted"] == 84.92

    def test_str_excludes_null_fields(self):
        result = CurrencyConversionResult(
            amount=100.0,
            from_currency="USD",
            to_currency="EUR",
            converted=84.92,
            rate=0.8492,
            rate_updated="2026-05-09",
        )
        assert '"error"' not in str(result)

    def test_error_result_contains_error_field(self):
        result = GeocodeResult(error="Location not found")
        parsed = json.loads(str(result))
        assert parsed["error"] == "Location not found"

    def test_error_result_excludes_unset_fields(self):
        result = GeocodeResult(error="Location not found")
        parsed = json.loads(str(result))
        assert "lat" not in parsed
        assert "lon" not in parsed


# ---------------------------------------------------------------------------
# calculate_trip_duration (pure Python — no mocking needed)
# ---------------------------------------------------------------------------

class TestCalculateTripDuration:
    def test_basic_two_week_trip(self):
        result = calculate_trip_duration.invoke(
            {"departure_date": "2026-08-01", "return_date": "2026-08-15"}
        )
        assert isinstance(result, TripDurationResult)
        assert result.total_days == 14
        assert result.weeks == 2
        assert result.remainder_days == 0
        assert result.error is None

    def test_odd_duration(self):
        result = calculate_trip_duration.invoke(
            {"departure_date": "2026-06-01", "return_date": "2026-06-14"}
        )
        assert result.total_days == 13
        assert result.weeks == 1
        assert result.remainder_days == 6

    def test_invalid_date_format(self):
        result = calculate_trip_duration.invoke(
            {"departure_date": "June 1 2026", "return_date": "2026-06-14"}
        )
        assert isinstance(result, TripDurationResult)
        assert result.error is not None
        assert result.total_days is None

    def test_return_before_departure(self):
        result = calculate_trip_duration.invoke(
            {"departure_date": "2026-06-14", "return_date": "2026-06-01"}
        )
        assert result.error is not None

    def test_future_trip_has_days_until(self):
        result = calculate_trip_duration.invoke(
            {"departure_date": "2030-01-01", "return_date": "2030-01-10"}
        )
        assert result.days_until_departure is not None
        assert result.days_until_departure > 0

    def test_result_serializes_to_json(self):
        result = calculate_trip_duration.invoke(
            {"departure_date": "2026-08-01", "return_date": "2026-08-15"}
        )
        parsed = json.loads(str(result))
        assert parsed["total_days"] == 14
        assert "error" not in parsed


# ---------------------------------------------------------------------------
# convert_currency (mocked HTTP)
# ---------------------------------------------------------------------------

MOCK_ER_RESPONSE = {
    "result": "success",
    "rates": {"EUR": 0.8492, "JPY": 156.66},
    "time_last_update_utc": "Sat, 09 May 2026 00:00:00 +0000",
}


class TestConvertCurrency:
    def test_successful_conversion(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_ER_RESPONSE
        with patch("tools.currency.requests.get", return_value=mock_resp):
            result = convert_currency.invoke(
                {"amount": 100.0, "from_currency": "USD", "to_currency": "EUR"}
            )
        assert isinstance(result, CurrencyConversionResult)
        assert result.error is None
        assert result.from_currency == "USD"
        assert result.to_currency == "EUR"
        assert result.converted == pytest.approx(84.92)
        assert result.rate == pytest.approx(0.8492)

    def test_unknown_target_currency(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_ER_RESPONSE
        with patch("tools.currency.requests.get", return_value=mock_resp):
            result = convert_currency.invoke(
                {"amount": 100.0, "from_currency": "USD", "to_currency": "XYZ"}
            )
        assert result.error is not None
        assert "XYZ" in result.error

    def test_api_error_response(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "error", "error-type": "invalid-key"}
        with patch("tools.currency.requests.get", return_value=mock_resp):
            result = convert_currency.invoke(
                {"amount": 100.0, "from_currency": "INVALID", "to_currency": "EUR"}
            )
        assert result.error is not None

    def test_result_serializes_to_json(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_ER_RESPONSE
        with patch("tools.currency.requests.get", return_value=mock_resp):
            result = convert_currency.invoke(
                {"amount": 500.0, "from_currency": "USD", "to_currency": "JPY"}
            )
        parsed = json.loads(str(result))
        assert parsed["from_currency"] == "USD"
        assert parsed["to_currency"] == "JPY"
        assert "error" not in parsed
