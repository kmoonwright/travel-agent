# Architecture Diagrams

---

## 1. System Topology

```
  ┌─────────────────────────────────────────────────────────────┐
  │  Docker Compose                                             │
  │                                                             │
  │  ┌──────────────────────────┐   ┌────────────────────────┐ │
  │  │  travel-assistant :8000  │   │  phoenix               │ │
  │  │                          │   │    :6006  UI            │ │
  │  │  FastAPI                 │   │    :4317  OTLP gRPC     │ │
  │  │  LangGraph Agent         │   │                        │ │
  │  │  OTel SDK ───────────────┼───┼──► OTLP receiver       │ │
  │  │                    spans │   │         │              │ │
  │  └──────────────────────────┘   │         ▼              │ │
  │                                 │   phoenix-data (vol)   │ │
  │                                 └────────────────────────┘ │
  └─────────────────────────────────────────────────────────────┘

  Client ──► POST /chat        ──► travel-assistant:8000
  Client ──► browse traces     ──► phoenix:6006
```

---

## 2. API Request Lifecycle

```
  Client
    │
    │  POST /chat  { message, session_id, user_id }
    ▼
  ┌─────────────────────────────────────────┐
  │  FastAPI  (api.py)                      │
  │                                         │
  │  using_attributes(session_id, user_id)  │
  │    └─ all child spans inherit context   │
  └──────────────────┬──────────────────────┘
                     │  agent.invoke(HumanMessage)
                     ▼
  ┌─────────────────────────────────────────┐
  │  LangGraph Agent                        │
  │                                         │
  │  ┌─────────────────────────────────┐    │
  │  │  llm_call                       │◄─┐ │
  │  │  GPT-4o + 11 tools bound        │  │ │
  │  └────────────────┬────────────────┘  │ │
  │                   │                   │ │
  │            tool_calls?                │ │
  │                   │                   │ │
  │          yes ─────┼──────────────┐    │ │
  │                   │              ▼    │ │
  │                   │  ┌───────────────┐│ │
  │                   │  │  tool_node    ││ │
  │                   │  │  invoke tool  ││ │
  │                   │  │  → JSON result│├─┘ │
  │                   │  └───────────────┘ │
  │          no ──────┘                    │
  └──────────────────┬─────────────────────┘
                     │  final AIMessage.content
                     ▼
  Client  { response: "..." }
```

---

## 3. LangGraph Agent Graph

```
       START
         │
         ▼
  ┌──────────────┐
  │   llm_call   │◄────────────────────┐
  │   GPT-4o     │                     │
  │   temp = 0   │                     │
  └──────┬───────┘                     │
         │                             │
    tool_calls?                        │
         │                             │
         ├── yes ──► ┌──────────────┐  │
         │           │  tool_node   │  │
         │           │  run tools   │──┘
         │           └──────────────┘
         │
         └── no ──► END

  State: messages: list[AnyMessage]
         append-only — full history preserved each loop
```

---

## 4. Evaluation Pipeline

```
  ┌─────────────────────┐
  │  eval/run_queries   │  10 POST /chat requests
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐          ┌──────────────────────────┐
  │  FastAPI :8000      │─ spans ──►  Arize Phoenix :6006      │
  └─────────────────────┘          └──────────────┬───────────┘
                                                  │
                                   get_spans_dataframe()
                                   root_spans_only=True
                                   filter: name == "LangGraph"
                                                  │
                                                  ▼
                                   ┌──────────────────────────┐
                                   │  pandas DataFrame        │
                                   │  one row per trace       │
                                   └──────────────┬───────────┘
                                                  │
                                                  ▼
                                   ┌──────────────────────────┐
                                   │  ClassificationEvaluator │
                                   │  model: GPT-4o-mini      │
                                   │  frustrated / ok         │
                                   └──────┬───────────────────┘
                                          │
                 ┌────────────────────────┼────────────────────┐
                 ▼                        ▼                    ▼
  ┌──────────────────────┐  ┌─────────────────────┐  ┌────────────────────┐
  │  Phoenix annotations │  │  eval/spans/*.csv   │  │  frustrated subset │
  │  Feedback panel      │  │  raw_spans.csv      │  │         │          │
  │  per-span label      │  │  frustration_eval   │  │         ▼          │
  │  + explanation       │  │  _results.csv       │  │  frustrated-       │
  └──────────────────────┘  └─────────────────────┘  │  interactions      │
                                                      │  Phoenix dataset   │
                                                      └────────────────────┘
```
