# Design Changes

This document records tool issues discovered during live testing and the design decisions made to fix them.

---

## Issue 1 — Weather tool skipped for future trip dates

### What broke
When a traveler asked *"What will the weather be like in Tokyo in July?"* (2 months away), the agent returned general seasonal knowledge from GPT-4o rather than calling the `get_weather` tool. No tool was invoked at all.

### Root cause
`get_weather` uses Open-Meteo's forecast API, which only returns a 7-day window from today. The LLM correctly inferred that calling the tool would produce irrelevant data (current week's forecast instead of July conditions) and skipped it entirely. This was the right call by the model, but left the user with unverified, undated information.

### Fix
Added a new `get_seasonal_climate` tool (`tools/climate.py`) that uses Open-Meteo's **archive API** (`archive-api.open-meteo.com/v1/archive`) to pull the previous year's actual daily data for a given city and month, then computes:
- Average high and low temperatures
- Hottest and coolest recorded days
- Total precipitation and number of rainy days

This provides historically grounded, data-backed seasonal expectations rather than model-generated generalizations. The tool accepts flexible month input ("July", "7", "jul").

Updated the system prompt in `agent.py` to explicitly instruct the model: use `get_weather` for trips within the next week, use `get_seasonal_climate` with the travel month for anything further out.

**Files changed:** `tools/climate.py` (new), `tools/__init__.py`, `agent.py`

---

## Issue 2 — Hotel search returned no results

### What broke
When asked to find hotels in Tokyo for July 10–20 under $200/night, the agent replied *"I couldn't retrieve specific hotel listings"* and gave up, pointing the user to booking platforms.

### Root cause
The DuckDuckGo query included the literal check-in and check-out dates:
```
"hotels in Tokyo check-in 2026-07-10 check-out 2026-07-20 2 guests under $200/night price availability rating"
```
DuckDuckGo is a general web search engine, not a booking engine. Date-specific availability queries like this match no real web pages and return empty or irrelevant results. The date strings actively degraded search quality.

### Fix
Removed the specific check-in/check-out dates from the search string entirely. The new query focuses on discoverable content that actually exists on the web: hotel guides, review articles, and comparison sites.

```python
# Before
query = f"hotels in {location} check-in {check_in} check-out {check_out} {guests} guests price availability rating"

# After
query = f"best hotels {location} {year} {budget_str}{nights_str}stay reviews recommended"
```

The year and night count are preserved as useful context (e.g., "10-night stay") without turning the query into a fake availability lookup.

Also switched from `DuckDuckGoSearchRun` (returns a flat text blob) to `DuckDuckGoSearchResults` (returns structured results with titles, URLs, and snippets), giving the LLM richer material to synthesize into named recommendations.

**Files changed:** `tools/hotels.py`

---

## Issue 3 — Travel advisory returned generic boilerplate

### What broke
When asked *"Is Japan safe to travel to?"*, the agent returned a generic description of how advisory levels work (Level 1–4 categories, embassy registration tips) without citing any specific advisory for Japan.

### Root cause
The DuckDuckGo query used Google-style `site:` operator syntax:
```
"travel advisory Japan 2026 safety warning level site:travel.state.gov OR site:gov.uk/foreign-travel-advice"
```
DuckDuckGo does not support multi-value `site:` OR filters. The operators were silently ignored or produced confused results. Without finding actual advisory pages, the LLM composed a generic safety explanation from its training data.

### Fix
Replaced the single query with two separate, natural-language queries — one targeting US State Department content, one targeting UK FCDO content — without any `site:` operators. DuckDuckGo naturally surfaces these authoritative sources when the query content matches their language:

```python
us_query = f"{country} travel advisory {year} US State Department safety level exercise normal caution"
uk_query = f"{country} FCDO foreign travel advice {year} safety entry requirements"
```

Both results are returned under labeled sections ("US State Department:" / "UK FCDO:"), letting the LLM synthesize a complete picture from both sources.

Also updated the advisory tool's docstring and the system prompt to instruct the model to call this tool for **all** destinations, not just "potentially unstable" ones. Safe countries like Japan still have official Level 1 advisories with entry requirements, health notices, and local law information that travelers benefit from knowing.

**Files changed:** `tools/advisories.py`, `agent.py`

---

## Issue 4 — Phoenix traces had no session or user context; tool fallbacks were invisible

### What broke

Traces in Phoenix showed all `/chat` requests as anonymous, with no way to filter by user or group a multi-turn conversation into a session. At the same time, when `search_attractions` or `search_restaurants` fell back from Overpass API to DuckDuckGo, the degradation was invisible — the span showed a successful tool call with no signal that the primary data source had failed.

### Root cause

**Session context:** `ChatRequest` had only a `message` field. No `session.id` or `user.id` was attached to any span, so Phoenix had no basis for filtering or grouping traces.

**Fallback visibility:** The Overpass `RequestException` was caught and silently swallowed (`except ...: pass`). The auto-instrumented TOOL span got no exception event and no attribute indicating degraded behavior.

### Fix

**Session context** — Added `session_id: str | None` and `user_id: str | None` to `ChatRequest`. The `/chat` endpoint now wraps the `agent.invoke()` call with `phoenix.otel.using_attributes()`, which propagates `session.id` (auto-generated UUID if not supplied) and `user.id` to every child span in the trace — including auto-instrumented LLM and tool spans — without any changes to agent or tool code. This follows the phoenix-tracing skill's guidance: setting the attribute on a parent span alone misses child spans; `using_attributes()` propagates automatically.

**Fallback visibility** — Changed `except requests.exceptions.RequestException as e` (was `as e` omitted) in both tools. After catching, the code now calls `trace.get_current_span().record_exception(e)` and sets `tool.fallback = True` on the existing auto-instrumented TOOL span. Phoenix can now surface fallback calls as degraded spans and they appear in exception flame graphs.

**Files changed:** `api.py`, `tools/attractions.py`, `tools/restaurants.py`

---

## Issue 5 — No evaluation of user experience in traces

### What was missing

After adding Phoenix tracing there was no way to distinguish whether users left a conversation satisfied or frustrated. All traces looked equally successful from an observability standpoint.

### Approach: user frustration evaluation

Added `evaluate_frustration.py` — a standalone offline script that:
1. Exports root spans from Phoenix (`root_spans_only=True`, filtered to `name == 'LangGraph'`)
2. Runs a GPT-4o-mini classification evaluator to label each trace `frustrated` or `ok`
3. Posts results as `user_frustration` annotations (visible in the Phoenix UI Feedback panel)
4. Creates a `frustrated-interactions` Phoenix dataset for downstream use (prompt iteration, fine-tuning, human review)

### Why root spans only

`root_spans_only=True` returns one row per trace — just the top-level LangGraph span. This is the right scope for frustration evaluation: the root span captures the full user input and the final assistant output, which is all the classifier needs. Evaluating at intermediate span level (LLM calls, tool calls) would produce multiple annotations per conversation with no added signal for frustration detection.

### Evaluation API: from old `llm_classify` to `ClassificationEvaluator`

The evaluation was originally intended to use `phoenix.evals.llm_classify` with a pre-tested `USER_FRUSTRATION_PROMPT_TEMPLATE` from Arize. After verifying the current `arize-phoenix-evals` package (v3.1.0), both `llm_classify` and `USER_FRUSTRATION_PROMPT_TEMPLATE` had been removed from the API. The correct current API uses:

```python
from phoenix.evals import ClassificationEvaluator, evaluate_dataframe
from phoenix.evals.llm import LLM

evaluator = ClassificationEvaluator(
    name="user_frustration",
    llm=LLM(provider="openai", model="gpt-4o-mini"),
    prompt_template=FRUSTRATION_PROMPT,
    choices={"frustrated": 1.0, "ok": 0.0},
    include_explanation=True,
)
results = evaluate_dataframe(dataframe=eval_df, evaluators=[evaluator])
```

`evaluate_dataframe` appends a `user_frustration_score` column containing a `Score` dict with `label`, `score`, and `explanation`.

### Evaluation methodology

**Evaluator:** `ClassificationEvaluator` (LLM-as-judge) with GPT-4o-mini. The prompt looks for: explicit complaints, ALL CAPS emphasis, references to repeated failures, demands with no tolerance for alternatives, negative comparisons to other tools, and ultimatums. The judge is instructed to assess the user's emotional state at the **end** of the conversation, not the beginning — a user who starts frustrated but gets a good answer should score `ok`.

**Label scheme:** binary `frustrated` / `ok` with scores 1.0 / 0.0.

**Input:** both the user message and the agent's final response are passed to the judge (`User: {msg}\nAssistant: {resp}`), giving context for whether the conversation resolved well.

**Result:** 11 traces evaluated; 4 classified as frustrated (the 3 intentional frustrated-user sessions plus one real borderline case). Annotations visible in Phoenix UI under each trace's Feedback panel.

**Files changed:** `pyproject.toml` (added `arize-phoenix-client`, `arize-phoenix-evals`), `evaluate_frustration.py` (new)

---

## Issue 6 — Tools returned formatted strings instead of structured output

### What was missing

All 11 tools returned Python `str` values — human-readable formatted text assembled with f-strings. While the LLM can parse these, the output is opaque to any downstream consumer (evaluators, dashboards, test assertions) that needs to extract individual fields. The assessment requirement explicitly asks for "structured output."

### Approach: Pydantic models with a JSON `__str__`

Added `tools/models.py` with a `TravelToolResult` base class and 14 concrete result models (including sub-models like `DailyForecast`, `Attraction`, `Restaurant`, `CurrentWeather`).

```python
class TravelToolResult(BaseModel):
    error: Optional[str] = None

    def __str__(self) -> str:
        return self.model_dump_json(indent=2, exclude_none=True)
```

The `__str__` override is the key design decision: LangChain's `ToolMessage(content=observation)` calls `str()` on the tool return value. By returning JSON from `__str__`, the LLM receives clean, structured JSON in its context window — no changes to `agent.py` required, and Phoenix traces now show JSON-formatted tool outputs rather than ad-hoc strings.

All error paths return the same model type with only the `error` field set, so callers always receive a consistent shape regardless of success or failure.

### Trade-off

JSON output is slightly more verbose than formatted strings but is unambiguously parseable by both LLMs and downstream code. GPT-4o handles JSON tool outputs well and can extract named fields more reliably than parsing free-form text.

**Files changed:** `tools/models.py` (new), all 11 tool files (`geo.py`, `time.py`, `weather.py`, `climate.py`, `attractions.py`, `restaurants.py`, `hotels.py`, `flights.py`, `currency.py`, `advisories.py`, `utils.py`)

---

## Issue 7 — Evaluator and span export had no permanent home

### What was missing

`evaluate_frustration.py` lived inside `travel-assistant/` with no exported artifacts. Step 4 of the assessment requires exporting spans from Phoenix; the evaluator only posted annotations back to Phoenix and created an in-product dataset — no local files that could be committed to the repo.

### Approach

Created an `eval/` directory at the project root with three files:

- `evaluate_frustration.py` (moved from `travel-assistant/`) — updated with CSV export: writes `eval/spans/raw_spans.csv` (all LangGraph root spans) and `eval/spans/frustration_eval_results.csv` (per-span labels, scores, and explanations) after each run.
- `run_queries.py` — sends 10 diverse travel queries to `POST /chat` with a shared `session_id`, generating the traces that the evaluator then consumes.

**Files changed:** `eval/evaluate_frustration.py` (moved + extended), `eval/run_queries.py` (new), `travel-assistant/evaluate_frustration.py` (deleted)

---

## Issue 9 — Eval query dataset was too small and homogeneous

### What was missing

`run_queries.py` sent 10 happy, well-formed travel queries all sharing a single `session_id` — they appeared as one session in Phoenix and provided no adversarial signal for the frustration evaluator to classify.

### Fix

Expanded to 20 queries with a per-query `session_id` and `user_id` persona (`user-01` through `user-20`), so each interaction appears as its own independent trace in Phoenix. 14 queries cover the full tool surface with realistic traveler requests. 6 queries simulate frustrated users using signals the evaluator detects: ALL CAPS emphasis, references to repeated failures ("I've asked THREE TIMES"), ultimatums ("I'm going back to Google"), and demands with no tolerance for alternatives. The stratified design ensures the frustration evaluator has enough adversarial examples to produce meaningful label distributions.

**Files changed:** `eval/run_queries.py`

---

## Issue 10 — No evaluation of agent output quality or system prompt adherence

### What was missing

The frustration evaluator measures how the user felt, but gives no signal about whether the agent actually answered the question or whether the new adventure/wonder system prompt is working as designed.

### Fix

Added `eval/evaluate_quality.py` with two `ClassificationEvaluator` judges running in a single `evaluate_dataframe()` call:

**`helpfulness`** — did the agent answer with specific, actionable information, or deflect with clarifying questions and generic advice? Catches a known failure mode of the new question-asking personality: a frustrated user demanding a direct answer who gets more questions instead. Input: full conversation (`User: … / Assistant: …`).

**`wonder`** — does the response lead with something vivid and specific and include an unexpected recommendation, directly testing system prompt adherence on destination queries? Short functional responses (exchange rates, time lookups) pass by default. Input: agent response only — the user message isn't relevant to voice quality.

Both post annotations to Phoenix alongside `user_frustration`, export to `eval/spans/quality_eval_results.csv`, and are designed to be re-run after any system prompt change as a quick regression signal.

**Files changed:** `eval/evaluate_quality.py` (new)

---

## Issue 8 — System prompt was task-oriented rather than traveler-centered

### What was missing

The agent answered questions accurately but treated every interaction the same way — a query in, facts out. It had no concept of who the traveler was, no mechanism for personalizing responses, and no voice beyond "be helpful and practical."

### Fix

Complete rewrite of `SYSTEM_PROMPT` in `agent.py` around three principles:

1. **Learn the traveler first.** When a destination is mentioned, ask 1–2 natural questions (who they're traveling with, first time there, what drew them) before jumping to information. Use what's learned to personalize every response that follows. The LangGraph `MessagesState` accumulates messages via `operator.add`, so context learned in one turn is available in all subsequent turns — no state changes required.

2. **Lead with wonder.** Open destination responses with something vivid and specific — the detail most people miss, what makes this place unlike anywhere else — before presenting practical information. Practical facts are framed as tools for the adventure, not a checklist.

3. **Always surface one unexpected recommendation.** Alongside the well-known, include one thing most guidebooks miss: a neighborhood, a market day, a lesser-known viewpoint.

Existing tool-use guidance (weather vs. seasonal climate, always call advisory tool, geocode before searching) is preserved verbatim, now framed as part of serving the traveler's experience rather than just factual accuracy.

**Files changed:** `agent.py`

---

## Summary table

| Area | Issue | Fix |
|------|-------|-----|
| `get_weather` | LLM skipped tool for future dates; 7-day window is useless for trip planning 2+ months out | New `get_seasonal_climate` tool using Open-Meteo archive API for historical monthly averages |
| `search_hotels` | Date-specific DuckDuckGo queries return no results | Remove dates from query; use location + budget + year; switch to `DuckDuckGoSearchResults` |
| `get_travel_advisory` | `site:` OR operator not supported by DuckDuckGo; generic boilerplate returned | Two separate natural-language queries targeting US/UK official advisory language |
| System prompt | Weather tool choice not guided; advisory tool not called for safe countries | Explicit guidance for when to use `get_seasonal_climate` vs `get_weather`; always call advisory tool |
| Tracing (all tools) | Anonymous traces; Overpass fallbacks invisible in Phoenix | `using_attributes()` propagates `session.id`/`user.id` to all spans; `record_exception()` + `tool.fallback=True` on degraded tool calls |
| Evaluation | No post-hoc evaluation of user experience | `evaluate_frustration.py` — GPT-4o-mini `ClassificationEvaluator` scores every trace; annotations + frustrated-interactions dataset created in Phoenix |
| All tools | String return values opaque to downstream consumers | `tools/models.py` — Pydantic `TravelToolResult` base with `exclude_none` JSON `__str__`; 11 typed return models |
| Eval + spans | Evaluator buried in application package; no local span export | `eval/` directory: `run_queries.py`, `evaluate_frustration.py`, `eval/spans/*.csv` committed |
| System prompt | Generic, task-oriented instructions; no traveler personalization or voice | Rewritten around adventure/wonder philosophy: ask 1–2 questions first, lead with vivid opening, always recommend the unexpected |
| Eval dataset | 10 homogeneous happy queries under one shared session | 20 queries with per-trace session/user IDs; 6 intentional frustrated-user personas for adversarial signal |
| Eval coverage | Only frustration measured (user signal) | Added `helpfulness` + `wonder` evaluators (agent signal); all three annotations posted per span |
