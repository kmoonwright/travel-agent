"""
Evaluate helpfulness and wonder adherence across travel-assistant traces in Phoenix.

Usage:
    poetry run python eval/evaluate_quality.py

Connects to Phoenix at localhost:6006, fetches root LangGraph spans, runs two
ClassificationEvaluator judges (GPT-4o-mini) in a single pass, and posts results
as span annotations.

  helpfulness  — did the agent actually answer the question vs. deflect?
  wonder       — does the response lead with evocative, specific writing vs. dry facts?
"""

import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "travel-assistant"))
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from phoenix.client import Client
from phoenix.evals import ClassificationEvaluator, evaluate_dataframe
from phoenix.evals.llm import LLM

from utils import (
    EVAL_MODEL,
    PHOENIX_URL,
    PROJECT_NAME,
    _extract_agent_response,
    _extract_user_message,
    _post_annotation,
)

HELPFULNESS_PROMPT = """\
You are evaluating whether an AI travel assistant gave a helpful response.

Conversation:
{input}

A helpful response:
- Directly addresses the user's travel question with specific, actionable information
- Uses real data (weather numbers, exchange rates, hotel options, attraction names) rather than generic advice
- Does not respond to a direct question with only more questions

An unhelpful response:
- Deflects the question entirely with clarifying questions and no substantive answer
- Gives only vague, generic travel advice ("research hotels", "check the weather", "consult a travel agent")
- Says it cannot provide the information requested without trying

Respond with exactly one word: "helpful" or "unhelpful"\
"""

WONDER_PROMPT = """\
You are evaluating whether an AI travel assistant's response reflects a sense of wonder and adventure.

Response:
{input}

A response that reflects wonder and adventure:
- Opens with something vivid, specific, or evocative about the destination — not just a list of facts
- Includes at least one specific, unexpected, or lesser-known recommendation (not just top tourist sites)
- Makes the destination feel alive and worth visiting, not just accurately described

A response that lacks wonder:
- Opens with generic statements ("X is a great city for travel") or immediately lists facts
- Only recommends the obvious tourist highlights with no personality
- Reads like a Wikipedia summary or a bullet-pointed checklist

Note: short functional responses (e.g. "The exchange rate is 32 THB to $1") are acceptable and should
be rated "wonder" — only penalise responses that describe a destination or make recommendations but
do so in a flat, guidebook-generic way.

Respond with exactly one word: "wonder" or "flat"\
"""


def main() -> None:
    client = Client(base_url=PHOENIX_URL)

    # --- 1. Fetch root LangGraph spans ----------------------------------------
    all_root = client.spans.get_spans_dataframe(
        project_name=PROJECT_NAME,
        root_spans_only=True,
        limit=500,
    )
    spans_df = all_root[all_root["name"] == "LangGraph"].copy()
    print(f"Found {len(spans_df)} LangGraph root spans to evaluate")

    if spans_df.empty:
        print("No spans found — is the travel-assistant project in Phoenix?")
        return

    # --- 2. Build eval DataFrame ----------------------------------------------
    records = []
    for span_id, row in spans_df.iterrows():
        user_msg = _extract_user_message(row.get("attributes.input.value") or "")
        agent_resp = _extract_agent_response(row.get("attributes.output.value") or "")
        if not user_msg or not agent_resp:
            continue
        records.append({
            "span_id": span_id,
            "session_id": row.get("attributes.session.id") or "",
            "user_message": user_msg,
            "agent_response": agent_resp,
            # helpfulness judges the full conversation
            "conversation": f"User: {user_msg}\nAssistant: {agent_resp}",
        })

    if not records:
        print("No spans had extractable messages.")
        return

    eval_df = pd.DataFrame(records)
    print(f"Running quality evaluators on {len(eval_df)} spans...\n")

    # --- 3. Helpfulness: input = full conversation ----------------------------
    helpfulness_df = eval_df.copy()
    helpfulness_df["input"] = helpfulness_df["conversation"]

    llm = LLM(provider="openai", model=EVAL_MODEL)

    helpfulness_eval = ClassificationEvaluator(
        name="helpfulness",
        llm=llm,
        prompt_template=HELPFULNESS_PROMPT,
        choices={"helpful": 1.0, "unhelpful": 0.0},
        include_explanation=True,
    )

    print("Evaluating helpfulness...")
    helpfulness_results = evaluate_dataframe(dataframe=helpfulness_df, evaluators=[helpfulness_eval])

    # --- 4. Wonder adherence: input = agent response only ---------------------
    wonder_df = eval_df.copy()
    wonder_df["input"] = wonder_df["agent_response"]

    wonder_eval = ClassificationEvaluator(
        name="wonder",
        llm=llm,
        prompt_template=WONDER_PROMPT,
        choices={"wonder": 1.0, "flat": 0.0},
        include_explanation=True,
    )

    print("\nEvaluating wonder adherence...")
    wonder_results = evaluate_dataframe(dataframe=wonder_df, evaluators=[wonder_eval])

    # --- 5. Post annotations --------------------------------------------------
    print("\nPosting annotations:")
    for i, (_, h_row) in enumerate(helpfulness_results.iterrows()):
        span_id = h_row["span_id"]
        h_score = h_row.get("helpfulness_score") or {}
        w_score = wonder_results.iloc[i].get("wonder_score") or {}

        _post_annotation(client, span_id, "helpfulness", h_score)
        _post_annotation(client, span_id, "wonder", w_score)

        h_label = str(h_score.get("label") or "?")
        w_label = str(w_score.get("label") or "?")
        session = str(h_row.get("session_id", ""))[:35]
        print(f"  [help={h_label:<10} wonder={w_label:<7}]  {session}")

    # --- 6. Export results ----------------------------------------------------
    merged = helpfulness_results[["span_id", "session_id", "user_message", "agent_response"]].copy()
    merged["helpfulness_label"] = helpfulness_results["helpfulness_score"].apply(
        lambda s: (s or {}).get("label", "")
    )
    merged["helpfulness_score"] = helpfulness_results["helpfulness_score"].apply(
        lambda s: float((s or {}).get("score", 0.0))
    )
    merged["wonder_label"] = wonder_results["wonder_score"].apply(
        lambda s: (s or {}).get("label", "")
    )
    merged["wonder_score"] = wonder_results["wonder_score"].apply(
        lambda s: float((s or {}).get("score", 0.0))
    )

    spans_dir = Path(__file__).parent / "spans"
    spans_dir.mkdir(exist_ok=True)
    out_path = spans_dir / "quality_eval_results.csv"
    merged.to_csv(out_path, index=False)
    print(f"\nExported results to {out_path}")

    helpful_count = (merged["helpfulness_label"] == "helpful").sum()
    wonder_count = (merged["wonder_label"] == "wonder").sum()
    total = len(merged)
    print(f"Helpfulness: {helpful_count}/{total} helpful")
    print(f"Wonder:      {wonder_count}/{total} wonder")
    print("\nView annotations in Phoenix: http://127.0.0.1:6006")


if __name__ == "__main__":
    main()
