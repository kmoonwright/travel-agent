"""
Send 20 diverse travel queries to the travel-assistant API to generate Phoenix traces.

Usage:
    poetry run python eval/run_queries.py

Requires the travel-assistant server to be running on localhost:8000.
Each query gets its own session_id and user_id so traces appear individually in Phoenix.
"""

import sys
import time
import uuid

import requests

BASE_URL = "http://127.0.0.1:8000"

# (message, user_id) — user_id lets Phoenix group by persona
QUERIES = [
    # --- happy / normal interactions ---
    ("What's the weather in Lisbon this weekend? I'm flying in Friday.", "user-01"),
    ("I'm planning my first solo trip to Japan in October — not sure where to start!", "user-02"),
    ("Can you find hotels in Amsterdam from June 3 to June 8 for 2 guests, budget around $150/night?", "user-03"),
    ("What's the USD to Thai Baht exchange rate right now?", "user-04"),
    ("What are the best things to do in Marrakech? We love food and architecture.", "user-05"),
    ("Is it safe to travel to Colombia right now?", "user-06"),
    ("My honeymoon is in the Amalfi Coast in September — what should we not miss?", "user-07"),
    ("I need flights from NYC to Tokyo in early April, 2 passengers economy.", "user-08"),
    ("What's the local time in Dubai right now?", "user-09"),
    ("We're taking our kids (ages 6 and 9) to Costa Rica. What should we know?", "user-10"),
    ("What's the weather typically like in Iceland in February?", "user-11"),
    ("I want to do a 10-day trip from May 12 to May 22. How many days is that exactly?", "user-12"),
    ("Any good ramen spots near Shinjuku, Tokyo?", "user-13"),
    ("What currency should I bring to Morocco, and how much is $500 worth in dirhams?", "user-14"),
    # --- frustrated interactions ---
    (
        "I've asked you THREE TIMES about cheap flights to Bali and you keep giving me generic search results. "
        "I need ACTUAL prices, not 'check booking sites' — that's completely useless.",
        "user-15",
    ),
    (
        "This is the second time I've asked about hotels in Prague and you still haven't given me anything useful. "
        "Every other travel site gives me real options. Why can't you?",
        "user-16",
    ),
    (
        "I don't want to answer your questions about who I'm traveling with. "
        "I JUST WANT THE WEATHER in Bangkok. Can you do that or not?",
        "user-17",
    ),
    (
        "I've been planning this trip for WEEKS and every time I ask for flight options from London to Cape Town "
        "you give me the same vague nonsense. This tool is a complete waste of time.",
        "user-18",
    ),
    (
        "Stop asking me about my 'travel style' and just tell me what to do in Barcelona. "
        "I'm not here for therapy, I'm here for information.",
        "user-19",
    ),
    (
        "Nothing you've told me about Santorini hotels has been helpful. "
        "Real prices? None. Specific availability? None. I'm going back to Google.",
        "user-20",
    ),
]


def run_query(message: str, user_id: str, index: int) -> None:
    session_id = str(uuid.uuid4())
    print(f"\n[{index + 1}/{len(QUERIES)}] ({user_id}) {message[:80]}{'...' if len(message) > 80 else ''}")
    try:
        resp = requests.post(
            f"{BASE_URL}/chat",
            json={"message": message, "session_id": session_id, "user_id": user_id},
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
    print("Travel Assistant Query Runner")
    print(f"Target: {BASE_URL}")

    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        health.raise_for_status()
    except requests.exceptions.RequestException:
        print(f"\nERROR: Server not reachable at {BASE_URL}")
        print("Start it with: docker-compose up -d")
        sys.exit(1)

    print(f"\nSending {len(QUERIES)} queries ({len(QUERIES) - 6} normal, 6 frustrated)...\n{'=' * 60}")

    for i, (message, user_id) in enumerate(QUERIES):
        run_query(message, user_id, i)
        if i < len(QUERIES) - 1:
            time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"Done. {len(QUERIES)} queries sent.")
    print("View traces at: http://127.0.0.1:6006")
    print("Run evaluation: poetry run python eval/evaluate_frustration.py")


if __name__ == "__main__":
    main()
