# Travel Assistant

A LangGraph agent that answers travel questions using 11 specialized tools — weather forecasts, seasonal climate data, attractions, restaurants, hotels, flights, currency conversion, local time, and travel advisories. Exposed via FastAPI with Arize Phoenix for trace observability and offline evaluation.

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Docker + Docker Compose (recommended)
- OpenAI API key

## Running with Docker Compose (recommended)

Docker Compose starts the travel assistant alongside a Phoenix observability server:

```bash
cp .env.example .env
# Add your OPENAI_API_KEY to .env

docker compose up
```

| Service | URL | Purpose |
|---------|-----|---------|
| Travel Assistant | http://localhost:8000 | API |
| Phoenix UI | http://localhost:6006 | Trace observability |

## Running locally (no Docker)

```bash
poetry install
cp .env.example .env
# Add your OPENAI_API_KEY to .env

poetry run uvicorn travel-assistant.api:app --reload
```

Phoenix tracing is skipped when `PHOENIX_COLLECTOR_ENDPOINT` is not set.

## API

### POST /chat

Send a message and get a travel assistant response. `session_id` groups traces for a conversation; `user_id` filters traces by user in Phoenix.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Plan a 10-day trip to Japan in April",
    "session_id": "user-123-conv-456",
    "user_id": "user-123"
  }'
```

```json
{ "response": "Here's a suggested 10-day Japan itinerary for April..." }
```

`session_id` and `user_id` are optional. A UUID is auto-generated for `session_id` if omitted.

### GET /tools — list available tools with descriptions
### GET /health — health check

## Tools

| Tool | Data Source | Use Case |
|------|-------------|----------|
| `get_weather` | Open-Meteo forecast | Current conditions / trips within 7 days |
| `get_seasonal_climate` | Open-Meteo archive | Historical averages for future trip planning |
| `search_attractions` | Overpass API (OSM) + DDG fallback | Museums, landmarks, points of interest |
| `search_restaurants` | Overpass API (OSM) + DDG fallback | Dining options with optional cuisine filter |
| `search_hotels` | DuckDuckGo | Hotel recommendations and reviews |
| `search_flights` | DuckDuckGo | Flight search results |
| `convert_currency` | ER-API | Live exchange rates |
| `get_local_time` | TimeAPI | Current local time at destination |
| `get_travel_advisory` | DuckDuckGo (US State Dept + UK FCDO) | Safety levels, entry requirements |
| `geocode_location` | Nominatim (OSM) | Internal — resolves city names to coordinates |
| `calculate_trip_duration` | — | Trip length in days from a date range |

## Agent Architecture

The agent is built with LangGraph as a two-node `StateGraph` that loops between an LLM and a tool executor until the model stops calling tools.

```
User message
     │
     ▼
┌─────────────┐
│  llm_call   │◄──────────────┐
│  (GPT-4o)   │               │
└──────┬──────┘               │
       │                      │
  tool calls?          ┌──────┴──────┐
       ├── yes ────────► tool_node   │
       │               │ (11 tools)  │
       └── no ──► END  └─────────────┘
```

**State** is an append-only `list[AnyMessage]`. Each `llm_call` prepends the system prompt and invokes GPT-4o with all 11 tools bound. If the model returns tool calls, `tool_node` executes each one and appends the results as `ToolMessage` objects. The loop continues until the model returns a plain text response.

The system prompt instructs the model when to use each tool — for example, using `get_seasonal_climate` (historical archive) instead of `get_weather` (7-day forecast) for trips more than a week out, and always calling `get_travel_advisory` for any destination regardless of perceived safety level.

## Observability

Traces are collected by [Arize Phoenix](https://docs.arize.com/phoenix) via OpenTelemetry. `auto_instrument=True` in `api.py` automatically patches LangChain and LangGraph, so every request produces a full trace without any changes to agent or tool code. Each trace captures:

- **LLM spans** — model name, token counts (input/output), full message history
- **Tool spans** — tool name, input arguments, output text
- **Graph node spans** — LangGraph `llm_call` and `tool_node` transitions

Every `/chat` request is wrapped in `phoenix.otel.using_attributes()`, which propagates `session.id` (auto-generated UUID if not supplied by the caller) and `user.id` to all child spans. This makes traces filterable and groupable by user or conversation in the Phoenix UI.

When `search_attractions` or `search_restaurants` falls back from Overpass to DuckDuckGo due to a network error, the span records the exception and sets `tool.fallback = true`, so degraded calls are distinguishable from successful primary lookups.

## Evaluation

After collecting traces, run the offline frustration evaluator:

```bash
poetry run python travel-assistant/evaluate_frustration.py
```

**What it does:**

1. Exports root spans from Phoenix (`root_spans_only=True`, filtered to `name == 'LangGraph'`) — one row per trace, containing the full user input and final agent response
2. Builds an eval DataFrame and runs a `ClassificationEvaluator` (GPT-4o-mini) against every span
3. Posts a `user_frustration` annotation to each span — visible in the Phoenix UI Feedback panel
4. Creates a `frustrated-interactions` dataset in Phoenix from all flagged traces

**Why root spans:** `root_spans_only=True` gives one row per trace rather than one row per LLM call or tool invocation. Frustration is a conversation-level signal — the full user input and final assistant output are all the classifier needs; intermediate spans add noise.

**Evaluator:** The GPT-4o-mini judge looks for signals in the user's message and the agent's response: explicit complaints, ALL CAPS emphasis, references to repeated failures, demands with no tolerance for alternatives, and negative comparisons to other tools. It assesses the user's emotional state at the **end** of the conversation — a user who starts frustrated but receives a satisfying answer scores `ok`.

**Output:** Binary label (`frustrated` / `ok`) with score 1.0 / 0.0. Annotations appear in the Phoenix trace Feedback panel. Frustrated traces are exported to a named `frustrated-interactions` dataset ready for prompt iteration, fine-tuning data, or human review.

## Project Structure

```
travel-agent/
├── pyproject.toml          # Poetry dependencies
├── docker-compose.yml      # Travel assistant + Phoenix co-container
├── Dockerfile
├── .env.example
└── travel-assistant/
    ├── agent.py                  # LangGraph graph definition
    ├── api.py                    # FastAPI server + Phoenix tracing setup
    ├── evaluate_frustration.py   # Offline user frustration evaluator
    ├── DESIGN-CHANGES.md         # Tool issues and design decisions log
    └── tools/
        ├── weather.py
        ├── climate.py
        ├── attractions.py
        ├── restaurants.py
        ├── hotels.py
        ├── flights.py
        ├── currency.py
        ├── time.py
        ├── advisories.py
        ├── geo.py
        └── utils.py
```
