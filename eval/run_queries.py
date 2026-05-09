"""
Send 10 diverse travel queries to the travel-assistant API to generate Phoenix traces.

Usage:
    poetry run python eval/run_queries.py

Requires the travel-assistant server to be running on localhost:8000.
All queries share a session_id so they appear as a single session in Phoenix.
"""

import sys
import time
import uuid

import requests

BASE_URL = "http://127.0.0.1:8000"
SESSION_ID = str(uuid.uuid4())
USER_ID = "eval-run"

QUERIES = [
    "What's the current weather like in Tokyo?",
    "Find me flights from San Francisco to Paris in late July for 2 passengers in economy.",
    "I'm looking for hotels in Barcelona from July 10 to July 17 for 2 guests under $200 a night.",
    "What are the top things to do in Kyoto, Japan?",
    "Can you find some good sushi restaurants in Tokyo?",
    "I need to convert 500 US dollars to Japanese yen.",
    "Is it safe to travel to Mexico City right now? What do the advisories say?",
    "My trip to Amsterdam is June 1 to June 14, 2026. How long is that?",
    "What's the typical weather like in Bali in August? I'm planning a trip.",
    "What time is it right now in Sydney, Australia?",
]


def run_query(message: str, index: int) -> None:
    print(f"\n[{index + 1}/10] {message}")
    try:
        resp = requests.post(
            f"{BASE_URL}/chat",
            json={"message": message, "session_id": SESSION_ID, "user_id": USER_ID},
            timeout=60,
        )
        resp.raise_for_status()
        response_text = resp.json().get("response", "")
        preview = response_text[:200].replace("\n", " ")
        print(f"  → {preview}{'...' if len(response_text) > 200 else ''}")
    except requests.exceptions.ConnectionError:
        print("  ERROR: Could not connect. Is the server running? (docker-compose up -d)")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}")


def main() -> None:
    print(f"Travel Assistant Query Runner")
    print(f"Session ID: {SESSION_ID}")
    print(f"Target: {BASE_URL}")

    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        health.raise_for_status()
    except requests.exceptions.RequestException:
        print(f"\nERROR: Server not reachable at {BASE_URL}")
        print("Start it with: docker-compose up -d")
        sys.exit(1)

    print(f"\nSending {len(QUERIES)} queries...\n{'=' * 60}")

    for i, query in enumerate(QUERIES):
        run_query(query, i)
        if i < len(QUERIES) - 1:
            time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"Done. {len(QUERIES)} queries sent.")
    print(f"Session ID: {SESSION_ID}")
    print("View traces at: http://127.0.0.1:6006")
    print("Run evaluation: poetry run python eval/evaluate_frustration.py")


if __name__ == "__main__":
    main()
