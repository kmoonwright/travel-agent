# Travel Assistant

A LangGraph-powered travel assistant that helps users plan trips through a conversational API. The agent uses GPT-4o with ten domain-specific tools to answer questions about weather, attractions, restaurants, flights, hotels, currency exchange, travel advisories, and more — all using free, keyless APIs. Only an OpenAI API key is required.

---

## Setup

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- An OpenAI API key

### Install

From the project root (`travel-agent/`):

```bash
poetry install
```

### Configure environment

Copy the example file and add your OpenAI key:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=sk-...
```

The travel assistant reads `.env` from the project root automatically — no separate configuration is needed inside `travel-assistant/`.

### Run the server

The server must be started from inside the `travel-assistant/` directory so that local package imports resolve correctly:

```bash
cd travel-assistant
poetry run uvicorn api:app --reload --port 8001
```

The API will be available at `http://localhost:8001`. Interactive docs (Swagger UI) are at `http://localhost:8001/docs`.

---

## API Endpoints

### `POST /chat`

Send a message to the travel assistant and receive a response.

**Request:**
```json
{ "message": "What is the weather like in Lisbon this week?" }
```

**Response:**
```json
{ "response": "Here's the weather forecast for Lisbon, Portugal this week..." }
```

**Example with curl:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to visit Tokyo in June. What should I know about weather, top attractions, and the USD to JPY exchange rate?"}'
```

### `GET /`

Redirects to the demo web UI at `/static/index.html`.

### `GET /health`

Health check. Returns `{"status": "ok"}`.

### `GET /tools`

Lists all available tools with their names and descriptions. Useful for understanding the agent's capabilities.

### `GET /config`

Returns `{"phoenix_project_id": "<id>"}` — proxies the Phoenix project ID so the web UI can construct deep links to traces without hitting Phoenix directly from the browser (avoids CORS issues in development).

---

## Agent Architecture

The agent is built with [LangGraph](https://langchain-ai.github.io/langgraph/) using a three-node cyclic graph. The graph state is a list of messages that accumulates across turns.

```
          ┌─────────────────────────────────────────────┐
          │                                             │
          ▼                                             │
        START                                          │
          │                                             │
          ▼                                             │
    ┌───────────┐                                       │
    │ llm_call  │  ── GPT-4o decides whether to call   │
    └─────┬─────┘     a tool or respond directly        │
          │                                             │
    ┌─────▼──────────────────────┐                     │
    │ should_continue (router)   │                     │
    └─────┬──────────────┬───────┘                     │
          │ tool_calls   │ no tool_calls               │
          ▼              ▼                              │
    ┌───────────┐      END                             │
    │ tool_node │  ── executes all requested tools ────┘
    └───────────┘     returns ToolMessages
```

**Nodes:**

- **`llm_call`** — Invokes GPT-4o with the full message history and a travel-focused system prompt. The model either returns a final response or requests one or more tool calls.
- **`tool_node`** — Iterates over all tool calls requested in the last message, executes each tool by name, and appends `ToolMessage` results to the state.
- **`should_continue`** — Conditional router. If the last message contains tool calls, routes to `tool_node`. Otherwise routes to `END`.

**State:**

```python
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
```

`operator.add` means every node return value is *appended* to the existing message list rather than replacing it. This gives the LLM the full conversation history at every step.

---

## Tools

All tools are `@tool`-decorated functions in `tools/`. The LLM reads each tool's docstring to decide when and how to invoke it.

| Tool | Source file | API used | Requires key |
|------|-------------|----------|:---:|
| `geocode_location` | `tools/geo.py` | Nominatim (OpenStreetMap) | No |
| `get_weather` | `tools/weather.py` | Open-Meteo forecast + Nominatim | No |
| `get_seasonal_climate` | `tools/climate.py` | Open-Meteo archive + Nominatim | No |
| `search_attractions` | `tools/attractions.py` | Overpass API (OpenStreetMap) | No |
| `search_restaurants` | `tools/restaurants.py` | Overpass API (OpenStreetMap) | No |
| `convert_currency` | `tools/currency.py` | open.er-api.com | No |
| `search_flights` | `tools/flights.py` | DuckDuckGo search | No |
| `search_hotels` | `tools/hotels.py` | DuckDuckGo search | No |
| `get_travel_advisory` | `tools/advisories.py` | DuckDuckGo search | No |
| `get_local_time` | `tools/time.py` | timeapi.io + Nominatim | No |
| `calculate_trip_duration` | `tools/utils.py` | Pure Python | No |

**Tool details:**

- **`geocode_location`** — Resolves a place name or address to coordinates, country, and display name. Also provides the internal `_geocode()` helper used by five other tools.

- **`get_weather`** — Returns current conditions and a 7-day forecast including temperatures, precipitation, and WMO weather condition descriptions. Supports Celsius or Fahrenheit. Use for trips within the next 7 days.

- **`get_seasonal_climate`** — Fetches the previous year's actual daily data from Open-Meteo's archive API for a given city and month, returning average highs/lows, total precipitation, and rainy-day count. Use for trip planning more than 7–10 days out.

- **`search_attractions`** — Queries OpenStreetMap for tourism and historic POIs within a configurable radius. Falls back to DuckDuckGo if Overpass returns no results or is unavailable.

- **`search_restaurants`** — Same Overpass pattern as attractions, filtering on `amenity=restaurant/cafe` with an optional cuisine tag. Falls back to DuckDuckGo.

- **`convert_currency`** — Fetches live rates from open.er-api.com for 160+ currencies and returns a formatted conversion with the rate update timestamp.

- **`search_flights`** — Constructs a targeted DuckDuckGo query for flights between origin and destination on a given date. Returns snippets with a note to verify on booking platforms.

- **`search_hotels`** — Same DuckDuckGo approach as flights, searching for hotels at a location between check-in and check-out dates with optional price cap.

- **`get_travel_advisory`** — Searches DuckDuckGo targeting `travel.state.gov` and `gov.uk/foreign-travel-advice` for safety information about a country.

- **`get_local_time`** — Geocodes the location, looks up its timezone from `timeapi.io`, then fetches the current local time including DST status.

- **`calculate_trip_duration`** — Pure Python date arithmetic. Given departure and return dates, returns total days, weeks/days breakdown, and how far away the departure is.

---

## Agent Workflow

A single request follows this path:

1. **User message arrives** at `POST /chat` as a `HumanMessage` and is passed to `agent.invoke()`.

2. **`llm_call`** prepends the system prompt to the message history and calls GPT-4o. The model has the full tool schema available and decides whether any tools are needed.

3. **`should_continue`** checks whether the model's response contains `tool_calls`.
   - If **yes**: route to `tool_node`.
   - If **no**: route to `END` and return the final response.

4. **`tool_node`** executes each requested tool call in sequence, collecting the results as `ToolMessage` objects. These are appended to the state.

5. **Loop back to `llm_call`** — the model now sees its own tool calls and their results and can either call more tools or compose a final response.

6. The loop continues until the model produces a message with no tool calls. The content of that final message is returned to the caller.

A complex query like *"Plan a week in Kyoto — what's the weather, top things to do, where to eat, and what is USD to JPY?"* will trigger the LLM to call `get_weather`, `search_attractions`, `search_restaurants`, and `convert_currency` in a single pass (GPT-4o can request multiple tools at once), then synthesize all results into one coherent response.

---

## Design Decisions

### Free APIs only — no additional API keys

The tools were designed to work with completely free, publicly accessible APIs. Nominatim, Open-Meteo, Overpass, open.er-api.com, and timeapi.io all operate without registration. This keeps the setup to a single credential (`OPENAI_API_KEY`) and avoids friction from rate-limited sandboxes or trial accounts.

### DuckDuckGo for flights and hotels

No free flight or hotel booking API returns reliably useful data without OAuth and sandbox limitations that produce mock results anyway. DuckDuckGo search with a structured query (`"flights from X to Y on date economy class"`) surfaces real current pricing and availability snippets from airline and aggregator sites. The tradeoff is that results are unstructured snippets rather than parsed data — the agent's system prompt instructs GPT-4o to summarize these into actionable options, and each tool appends a tip to verify on a booking platform.

### Overpass API with DuckDuckGo fallback

Overpass is a free query interface to the full OpenStreetMap dataset, making it ideal for real POI data without a key. However, it is a shared community resource that can be slow or temporarily overloaded. The fallback to DuckDuckGo ensures the agent always returns something useful — it simply labels the results as "web search" so the difference is transparent to the user.

### Tools return formatted strings, not JSON

LangChain tool results are injected into the message history as `ToolMessage` content. The LLM reads this content directly when composing its response. Plain-text formatted strings (e.g., `"Current: 18°C, Partly cloudy, Humidity: 65%"`) are more token-efficient than JSON and reduce the model's work in parsing and re-formatting. Structured JSON would only be preferable if the results needed programmatic processing downstream.

### `temperature=0` on the LLM

Travel information needs to be factually consistent. With `temperature=0` the model is deterministic — it will call the same tools and compose the same structure given the same input. This makes the agent's behavior predictable and easier to debug.

### `sys.path` manipulation for local imports

Because `travel-assistant/` uses a `tools/` sub-package with relative imports, and `pyproject.toml` sets `package-mode = false`, running `uvicorn api:app` from inside the directory requires `travel-assistant/` to be on `sys.path`. Both `agent.py` and `api.py` prepend their own directory at the top using `sys.path.insert(0, str(Path(__file__).parent))`. This is done before any local imports and is idempotent if the path is already present.

### Single `.env` at the project root

`load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")` resolves to the project root's `.env` regardless of where uvicorn is invoked from. This avoids duplicating credentials across the root and `travel-assistant/` directories.
