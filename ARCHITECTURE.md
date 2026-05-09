# Architecture Diagrams

---

## 1. System Topology

```
                         Docker Compose
  +----------------------------------------------------------+
  |                                                          |
  |  +------------------------+    +---------------------+  |
  |  |  travel-assistant      |    |  phoenix            |  |
  |  |  :8000                 |    |  :6006  (UI)        |  |
  |  |                        |    |  :4317  (OTLP gRPC) |  |
  |  |  FastAPI               |    |                     |  |
  |  |  LangGraph Agent       | -- |  Phoenix UI         |  |
  |  |  OTel SDK  ------------|----|--> OTLP receiver    |  |
  |  |                        | spans                    |  |
  |  +------------------------+    +---------------------+  |
  |                                         |               |
  +------------------------------------------|--------------+
                                             |
                                     phoenix-data (volume)

  Client --> POST /chat       --> travel-assistant:8000
  Client --> browse traces    --> phoenix:6006
```

---

## 2. API Request Lifecycle

```
  Client
    |
    |  POST /chat  { message, session_id, user_id }
    v
  FastAPI (api.py)
    |
    |  using_attributes(session_id, user_id)
    |    all child spans inherit session + user context
    |
    |  agent.invoke(HumanMessage)
    v
  LangGraph Agent
    |
    +--[loop until no tool_calls]----------------------------+
    |                                                        |
    |  invoke GPT-4o with system prompt + message history   |
    |    |                                                   |
    |    v                                                   |
    |  AIMessage                                             |
    |    |                                                   |
    |    +-- tool_calls present?                             |
    |         |                                              |
    |        yes --> tool.invoke(args)                       |
    |                  |                                     |
    |                  v                                     |
    |               TravelToolResult (JSON)                  |
    |                  |                                     |
    |               append ToolMessage --> back to top       |
    |                                                        |
    +--[no tool_calls]----------------------------------------+
    |
    v
  final AIMessage.content
    |
    v
  Client  { response: "..." }
```

---

## 3. LangGraph Agent Graph

```
  START
    |
    v
  +-------------+
  |  llm_call   |<--------------------------+
  |  GPT-4o     |                           |
  |  temp=0     |                           |
  +------+------+                           |
         |                                  |
         v                                  |
    tool_calls?                             |
         |                                  |
        yes --> +-------------+             |
                |  tool_node  |-------------+
                |  run tools  |
                +-------------+
         |
        no
         |
         v
        END
```

State: `messages: list[AnyMessage]`  — append-only, full history preserved across every loop iteration.

---

## 4. Evaluation Pipeline

```
  eval/run_queries.py
    | 10 POST /chat requests
    v
  FastAPI :8000
    | OTel spans
    v
  Arize Phoenix  (localhost:6006)
    |
    |  client.spans.get_spans_dataframe(root_spans_only=True)
    |  filter: name == "LangGraph"
    v
  pandas DataFrame  -- one row per trace
    |
    |  ClassificationEvaluator
    |  model: GPT-4o-mini
    |  prompt: frustration signals
    |  labels: frustrated (1.0) / ok (0.0)
    v
  Results DataFrame
    |
    +-----------------------------+----------------------------+
    |                             |                            |
    v                             v                            v
  Phoenix annotations       eval/spans/               frustrated subset
  (Feedback panel)          raw_spans.csv                     |
  user_frustration label    frustration_eval_results.csv      v
  on each trace                                     frustrated-interactions
                                                    Phoenix named dataset
```
