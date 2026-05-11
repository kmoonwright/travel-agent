# Architecture Diagrams

---

## 1. System Topology

```
  ┌────────────────────────────────────────────────────────────┐
  │  Docker Compose                                            │
  │                                                            │
  │  ┌──────────────────────────┐   ┌────────────────────────┐ │
  │  │  travel-assistant :8000  │   │  phoenix               │ │
  │  │                          │   │    :6006  UI + OTLP    │ │
  │  │  FastAPI                 │   │                        │ │
  │  │  LangGraph Agent         │   │                        │ │
  │  │  OTel SDK ───────────────┼───┼──► OTLP receiver       │ │
  │  │                    spans │   │         │              │ │
  │  └──────────────────────────┘   │         ▼              │ │
  │                                 │   phoenix-data (vol)   │ │
  │                                 └────────────────────────┘ │
  └────────────────────────────────────────────────────────────┘

  Client ──► POST /chat        ──► travel-assistant:8000
  Client ──► browse traces     ──► phoenix:6006
```

---

## 2. Agent Request Flow

```
  Client
    │
    │  POST /chat  { message, session_id, user_id }
    ▼
  ┌──────────────────────────────────────────┐
  │  FastAPI  (api.py)                       │
  │  using_attributes(session_id, user_id)   │
  │    └─ all child spans inherit context    │
  └───────────────────┬──────────────────────┘
                      │  agent.invoke(HumanMessage)
                      ▼
  ┌──────────────────────────────────────────┐
  │  LangGraph Agent                         │
  │                                          │
  │  ┌──────────────────────────────────┐    │
  │  │  llm_call  (GPT-4o, temp=0)      │◄─┐ │
  │  └─────────────────┬────────────────┘  │ │
  │                    │                   │ │
  │             tool_calls?                │ │
  │                    │                   │ │
  │           yes ─────┴──────────────┐    │ │
  │                                   ▼    │ │
  │                   ┌───────────────────┐│ │
  │                   │  tool_node        ││ │
  │                   │  get_weather      ││ │
  │                   │  search_flights   ││ │
  │                   │  search_hotels    ││ │
  │                   │  convert_currency ││ │
  │                   │  get_travel_adv.  │┘ │
  │                   │  + 6 more         │  │ 
  │                   └───────────────────┘  │
  │           no ─────────────────────┐      │
  └───────────────────┬───────────────┴──────┘
                      │  final AIMessage.content
                      ▼
  Client  { response: "..." }

  State: messages: list[AnyMessage]  (append-only, full history each loop)
```

---

## 3. Evaluation Pipeline

```
  ┌─────────────────────┐
  │  eval/run_queries   │  20 POST /chat requests (14 normal + 6 frustrated personas)
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐          ┌──────────────────────────┐
  │  FastAPI :8000      │─ spans ──►  Arize Phoenix :6006     │
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
                                   └──────┬─────────┬─────────┘
                                          │         │
                              ┌───────────┘         └───────────┐
                              ▼                                 ▼
               ┌──────────────────────────┐   ┌──────────────────────────┐
               │  evaluate_frustration.py │   │  evaluate_quality.py     │
               │  ClassificationEvaluator │   │  ClassificationEvaluator │
               │  frustrated / ok         │   │  helpfulness: helpful /  │
               │                          │   │    unhelpful             │
               └──────────┬───────────────┘   │  wonder: wonder / flat   │
                          │                   └──────────┬───────────────┘
                          │                              │
                 ┌────────┴──────────────────────────────┤
                 ▼                        ▼              ▼
  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐
  │  Phoenix annotations │  │  eval/spans/*.csv    │  │  frustrated subset │
  │  Feedback panel      │  │  raw_spans.csv       │  │         │          │
  │  user_frustration    │  │  frustration_eval    │  │         ▼          │
  │  helpfulness         │  │    _results.csv      │  │  frustrated-       │
  │  wonder              │  │  quality_eval        │  │  interactions      │
  └──────────────────────┘  │    _results.csv      │  │  Phoenix dataset   │
                            └──────────────────────┘  └────────────────────┘
```

