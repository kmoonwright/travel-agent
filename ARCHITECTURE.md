# Architecture Diagrams

Six diagrams covering every architectural layer of the travel assistant.

---

## 1. System Topology

Docker Compose runs two services. The travel assistant sends OpenTelemetry spans to Phoenix over gRPC; Phoenix exposes its UI on port 6006.

```mermaid
graph TD
    Client["Client\n(curl / browser)"]

    subgraph docker ["Docker Compose Network"]
        direction TB

        subgraph ta ["travel-assistant  :8000"]
            API["FastAPI\napi.py"]
            Agent["LangGraph Agent\nagent.py"]
            Tools["11 Tools\ntools/"]
            OTel["OTel SDK\nauto_instrument=True"]
        end

        subgraph ph ["phoenix  :6006 / :4317"]
            PhUI["Phoenix UI\nlocalhost:6006"]
            PhOTLP["OTLP gRPC receiver\n:4317"]
            PhData[("phoenix-data\nvolume")]
        end

        API --> Agent
        Agent --> Tools
        OTel -. "OTLP gRPC\nspans" .-> PhOTLP
        PhOTLP --> PhData
        PhData --> PhUI
    end

    Client -- "POST /chat\nGET /health\nGET /tools" --> API
    Client -- "browse traces" --> PhUI

    style ta fill:#e8f4f8,stroke:#2196F3
    style ph fill:#fef3e2,stroke:#FF9800
```

**Key wiring:** `PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006` is set in `docker-compose.yml`. The health-check dependency ensures Phoenix is ready before the travel assistant starts.

---

## 2. API Request Lifecycle

Sequence of a single `POST /chat` call from client to response, showing where Phoenix context is attached.

```mermaid
sequenceDiagram
    participant C as Client
    participant F as FastAPI (api.py)
    participant P as Phoenix OTel
    participant G as LangGraph Agent
    participant O as OpenAI GPT-4o
    participant T as Tool

    C->>F: POST /chat {message, session_id, user_id}
    F->>P: using_attributes(session_id, user_id)
    Note over P: All child spans inherit<br/>session.id + user.id

    F->>G: agent.invoke({messages: [HumanMessage]})

    loop until no tool_calls
        G->>O: model_with_tools.invoke([SystemMessage] + messages)
        O-->>G: AIMessage (may contain tool_calls)

        opt tool_calls present
            G->>T: tool.invoke(args)
            T-->>G: TravelToolResult (JSON via __str__)
            G->>G: append ToolMessage(content=str(result))
        end
    end

    G-->>F: final AIMessage.content
    F-->>C: {response: "..."}
    F->>P: tracer_provider.force_flush()
```

---

## 3. LangGraph Agent Graph

The compiled `StateGraph` — nodes, edges, and the conditional router that drives the tool-call loop.

```mermaid
flowchart TD
    subgraph state ["MessagesState"]
        MS["messages: Annotated[list[AnyMessage], operator.add]\n(append-only — full history preserved)"]
    end

    START(["START"]) --> llm_call

    subgraph loop ["Agent Loop"]
        llm_call["llm_call\nChatOpenAI gpt-4o · temp=0\nbinds all 11 tools"]
        sc{"should_continue\nlast_message.tool_calls?"}
        tool_node["tool_node\ntools_by_name[name].invoke(args)\n→ ToolMessage(content=str(result))"]

        llm_call --> sc
        sc -- "tool_calls present" --> tool_node
        tool_node -- "append ToolMessages" --> llm_call
    end

    sc -- "no tool_calls" --> END(["END\nreturn last AIMessage"])

    state -.->|read + append| loop
```

---

## 4. Tool Ecosystem

### 4a — Tools and their data sources

```mermaid
graph LR
    subgraph agent ["LangGraph Agent"]
        TN["tool_node"]
    end

    subgraph tools ["11 Tools (tools/)"]
        GW["get_weather"]
        GSC["get_seasonal_climate"]
        SA["search_attractions"]
        SR["search_restaurants"]
        SH["search_hotels"]
        SF["search_flights"]
        CC["convert_currency"]
        GTA["get_travel_advisory"]
        GLT["get_local_time"]
        GL["geocode_location"]
        CTD["calculate_trip_duration"]
    end

    subgraph apis ["External APIs (all free)"]
        OM_F["Open-Meteo\nForecast API"]
        OM_A["Open-Meteo\nArchive API"]
        NOM["Nominatim\nOpenStreetMap"]
        OVP["Overpass API\nOSM"]
        DDG["DuckDuckGo\nSearch"]
        ERA["ER-API\nExchange Rates"]
        TAPI["timeapi.io"]
        PY["Pure Python\n(no API)"]
    end

    TN --> GW & GSC & SA & SR & SH & SF & CC & GTA & GLT & GL & CTD

    GW --> OM_F
    GW --> NOM
    GSC --> OM_A
    GSC --> NOM
    SA --> NOM
    SA --> OVP
    SA -. "fallback" .-> DDG
    SR --> NOM
    SR --> OVP
    SR -. "fallback" .-> DDG
    SH --> DDG
    SF --> DDG
    GTA --> DDG
    CC --> ERA
    GLT --> NOM
    GLT --> TAPI
    GL --> NOM
    CTD --> PY

    style SA fill:#fff3cd,stroke:#ffc107
    style SR fill:#fff3cd,stroke:#ffc107
```

### 4b — Pydantic structured output model hierarchy

All tools return a typed subclass of `TravelToolResult`. The base class serializes to JSON via `model_dump_json(exclude_none=True)`.

```mermaid
graph TD
    BASE["TravelToolResult\n— error: Optional[str]\n— __str__() → JSON"]

    BASE --> GEO["GeocodeResult\n— display_name, lat, lon, country"]
    BASE --> LT["LocalTimeResult\n— location, datetime_str,\n  timezone, dst_active"]
    BASE --> WR["WeatherResult\n— city, units\n— current: CurrentWeather\n— forecast: list[DailyForecast]"]
    BASE --> CR["ClimateResult\n— city, month, units\n— avg_high/low, max/min_temp\n— total_precip_mm, rainy_days\n— reference_year"]
    BASE --> ASR["AttractionSearchResult\n— location, radius_km, source\n— attractions: list[Attraction]"]
    BASE --> RSR["RestaurantSearchResult\n— location, cuisine_filter\n— restaurants: list[Restaurant]"]
    BASE --> HSR["HotelSearchResult\n— location, check_in, check_out\n— guests, nights, search_results"]
    BASE --> FSR["FlightSearchResult\n— origin, destination, date\n— cabin_class, passengers\n— search_results"]
    BASE --> CCR["CurrencyConversionResult\n— amount, from/to_currency\n— converted, rate, rate_updated"]
    BASE --> TAR["TravelAdvisoryResult\n— country\n— us_advisory, uk_advisory"]
    BASE --> TDR["TripDurationResult\n— departure_date, return_date\n— total_days, weeks\n— remainder_days\n— days_until_departure"]

    WR --> CW["CurrentWeather\n— temperature, humidity_pct\n— wind_speed_kmh, condition"]
    WR --> DF["DailyForecast\n— date, condition\n— high, low, precipitation_mm"]
    ASR --> AT["Attraction\n— name, category"]
    RSR --> RS["Restaurant\n— name, cuisine, address"]

    style BASE fill:#d4edda,stroke:#28a745,font-weight:bold
```

---

## 5. OpenTelemetry Span Hierarchy

Anatomy of a single trace produced by one `POST /chat` request. Spans are nested by parent-child relationship; the root span is what the evaluator reads.

```mermaid
graph TD
    ROOT["🔷 LangGraph  ← ROOT SPAN\nattributes:\n  session.id · user.id\n  input.value · output.value\n  openinference.span.kind = CHAIN"]

    ROOT --> LC1["🟦 llm_call  node span"]
    LC1  --> OAI1["🟣 ChatOpenAI  LLM span\nattributes:\n  llm.model_name = gpt-4o\n  llm.token_count.prompt\n  llm.token_count.completion\n  llm.input_messages[]"]

    ROOT --> TN["🟦 tool_node  node span"]
    TN   --> TS["🟠 convert_currency  TOOL span\nattributes:\n  tool.name\n  openinference.span.kind = TOOL\ninput: {amount, from_currency, to_currency}\noutput: {converted, rate, ...} ← JSON"]

    ROOT --> LC2["🟦 llm_call  node span  (2nd iteration)"]
    LC2  --> OAI2["🟣 ChatOpenAI  LLM span\n(synthesizes final answer)"]

    subgraph fallback ["Fallback path — when Overpass unavailable"]
        TN2["🟦 tool_node"]
        TS2["🔴 search_attractions  TOOL span\nevents: RequestException recorded\nattributes: tool.fallback = true"]
        TN2 --> TS2
    end

    style ROOT fill:#cce5ff,stroke:#004085,font-weight:bold
    style OAI1 fill:#e8d5f5,stroke:#6f42c1
    style OAI2 fill:#e8d5f5,stroke:#6f42c1
    style TS fill:#ffe5cc,stroke:#e65c00
    style TS2 fill:#f8d7da,stroke:#721c24
    style LC1 fill:#d1ecf1,stroke:#0c5460
    style LC2 fill:#d1ecf1,stroke:#0c5460
    style TN fill:#d1ecf1,stroke:#0c5460
```

---

## 6. Evaluation Pipeline

Offline flow from trace generation through frustration scoring to exported artifacts.

```mermaid
flowchart TD
    RQ["eval/run_queries.py\n10 diverse POST /chat requests\nshared session_id"]

    RQ -- "HTTP requests" --> API["FastAPI :8000"]
    API -- "OTel spans" --> PH[("Arize Phoenix\nlocalhost:6006")]

    PH -- "get_spans_dataframe\nroot_spans_only=True" --> DF["pandas DataFrame\none row per trace"]

    DF -- "filter name == 'LangGraph'" --> FILT["LangGraph root spans\n(exclude standalone DDG spans)"]

    FILT -- "extract user_message\n+ agent_response" --> EVAL_IN["Eval DataFrame\ninput = 'User: ...\nAssistant: ...'"]

    EVAL_IN --> EVA["ClassificationEvaluator\nmodel: GPT-4o-mini\nprompt: frustration signals\nchoices: frustrated=1.0 / ok=0.0"]

    EVA --> RESULTS["Results DataFrame\n+ user_frustration_score\n  { label, score, explanation }"]

    RESULTS --> ANN["client.spans.add_span_annotation()\n→ Phoenix Feedback panel\n   user_frustration label per trace"]

    RESULTS --> CSV1["eval/spans/\nfrustration_eval_results.csv\n(all spans: label + explanation)"]

    RESULTS -- "filter label == frustrated" --> FRUS["Frustrated subset"]

    FRUS --> DS["client.datasets.create_dataset()\n→ 'frustrated-interactions'\n   Phoenix named dataset"]

    PH -- "all root spans export" --> CSV2["eval/spans/\nraw_spans.csv\n(full span attributes)"]

    style PH fill:#fef3e2,stroke:#FF9800
    style EVA fill:#e8f4f8,stroke:#2196F3
    style DS fill:#d4edda,stroke:#28a745
    style CSV1 fill:#d4edda,stroke:#28a745
    style CSV2 fill:#d4edda,stroke:#28a745
```
