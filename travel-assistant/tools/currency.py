import requests
from langchain_core.tools import tool

from .models import CurrencyConversionResult

ER_API_URL = "https://open.er-api.com/v6/latest/{base}"


@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> CurrencyConversionResult:
    """Convert an amount between currencies using live exchange rates.

    Use this when a traveler needs to know how much their money is worth
    in their destination's currency, or to budget a trip.

    Args:
        amount: Amount to convert (e.g., 100.0)
        from_currency: Source currency ISO 4217 code (e.g., "USD", "EUR", "GBP")
        to_currency: Target currency ISO 4217 code (e.g., "JPY", "THB", "AUD")
    """
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    try:
        resp = requests.get(ER_API_URL.format(base=from_currency), timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != "success":
            return CurrencyConversionResult(error=f"Exchange rate error for '{from_currency}': {data.get('error-type', 'unknown')}. Use ISO 4217 codes (USD, EUR, GBP, JPY, etc.).")

        rates = data.get("rates", {})
        if to_currency not in rates:
            return CurrencyConversionResult(error=f"Unknown currency code '{to_currency}'. Use ISO 4217 format (e.g., USD, EUR, GBP, JPY).")

        rate = rates[to_currency]

        return CurrencyConversionResult(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            converted=round(amount * rate, 2),
            rate=rate,
            rate_updated=data.get("time_last_update_utc", "unknown"),
        )

    except requests.exceptions.RequestException as e:
        return CurrencyConversionResult(error=f"Exchange rate service unavailable: {e}. Please try again.")
