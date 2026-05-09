"""
Evaluate user frustration across travel-assistant traces in Phoenix.

Usage:
    poetry run python travel-assistant/evaluate_frustration.py

Connects to Phoenix at localhost:6006, fetches root LangGraph spans
(one per trace), runs a ClassificationEvaluator (GPT-4o-mini judge) to
detect user frustration, posts results as span annotations, and uploads
a dataset of frustrated interactions.
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from phoenix.client import Client
from phoenix.evals import ClassificationEvaluator, evaluate_dataframe
from phoenix.evals.llm import LLM

PHOENIX_URL = "http://127.0.0.1:6006"
PROJECT_NAME = "travel-assistant"
EVAL_MODEL = "gpt-4o-mini"
DATASET_NAME = "frustrated-interactions"

FRUSTRATION_PROMPT = """\
You are evaluating whether a user is frustrated with an AI travel assistant.

Conversation:
{input}

Signs of frustration: explicit complaints ("this is useless", "nothing is working",
"I've been trying for weeks"), ALL CAPS emphasis, references to repeated failures
("I've asked three times already", "last time you gave me garbage"), demands with no
tolerance for alternatives ("I want X not Y, just do it"), negative comparisons to
other tools, ultimatums or threats to stop using the service.

Assess the user's emotional state at the end of the conversation. Respond with exactly
one word: "frustrated" or "ok"."""


def _extract_user_message(input_value: str) -> str:
    try:
        data = json.loads(input_value)
        for msg in data.get("messages", []):
            if msg.get("type") == "human":
                return msg.get("data", {}).get("content") or msg.get("content", "")
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return ""


def _extract_agent_response(output_value: str) -> str:
    try:
        data = json.loads(output_value)
        for msg in reversed(data.get("messages", [])):
            if msg.get("type") == "ai":
                content = msg.get("data", {}).get("content") or msg.get("content", "")
                if content:
                    return content
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return ""


def main() -> None:
    client = Client(base_url=PHOENIX_URL)

    # --- 1. Export root spans -------------------------------------------------
    # root_spans_only=True gives one row per trace — just the top-level span.
    # That's the right scope for frustration evaluation: we want the full user
    # input and final assistant output, not every intermediate LLM call or tool
    # invocation. We additionally filter to name == 'LangGraph' because DDG tool
    # spans also surface as roots (they have no parent_id) but don't carry the
    # conversation context we need.
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
        if not user_msg:
            continue
        records.append({
            "span_id": span_id,
            "session_id": row.get("attributes.session.id") or "",
            "user_id": row.get("attributes.user.id") or "",
            "user_message": user_msg,
            "agent_response": agent_resp,
            # "input" is the column the prompt template's {input} placeholder maps to
            "input": f"User: {user_msg}\nAssistant: {agent_resp}",
        })

    if not records:
        print("No spans had extractable user messages.")
        return

    eval_df = pd.DataFrame(records)
    print(f"Running '{EVAL_MODEL}' frustration classifier on {len(eval_df)} spans...\n")

    # --- 3. Run ClassificationEvaluator ---------------------------------------
    llm = LLM(provider="openai", model=EVAL_MODEL)
    evaluator = ClassificationEvaluator(
        name="user_frustration",
        llm=llm,
        prompt_template=FRUSTRATION_PROMPT,
        choices={"frustrated": 1.0, "ok": 0.0},
        include_explanation=True,
    )
    results = evaluate_dataframe(dataframe=eval_df, evaluators=[evaluator])
    # evaluate_dataframe appends: user_frustration_score, user_frustration_label,
    # user_frustration_explanation

    # --- 4. Post annotations to Phoenix ---------------------------------------
    # evaluate_dataframe returns user_frustration_score as a Score dict:
    # {"label": "frustrated"|"ok", "score": 1.0|0.0, "explanation": "...", ...}
    print("\nPosting annotations:")
    for _, row in results.iterrows():
        span_id = row["span_id"]
        score_obj = row.get("user_frustration_score") or {}
        label = str(score_obj.get("label") or "ok")
        score = float(score_obj.get("score") or 0.0)
        explanation = str(score_obj.get("explanation") or "")

        client.spans.add_span_annotation(
            span_id=span_id,
            annotation_name="user_frustration",
            annotator_kind="LLM",
            label=label,
            score=score,
            explanation=explanation,
            metadata={"model": EVAL_MODEL},
            sync=True,
        )
        tag = "FRUSTRATED" if label == "frustrated" else "ok      "
        session = str(row.get("session_id", ""))[:35]
        print(f"  [{tag}]  {session}")

    # --- 5. Create dataset of frustrated interactions -------------------------
    results["_label"] = results["user_frustration_score"].apply(
        lambda s: (s or {}).get("label", "ok")
    )
    results["_score"] = results["user_frustration_score"].apply(
        lambda s: float((s or {}).get("score", 0.0))
    )
    results["_explanation"] = results["user_frustration_score"].apply(
        lambda s: (s or {}).get("explanation", "")
    )

    frustrated = results[results["_label"] == "frustrated"].copy()
    print(f"\n{len(frustrated)} / {len(results)} spans classified as frustrated")

    if not frustrated.empty:
        dataset_df = frustrated[[
            "span_id", "session_id", "user_id",
            "user_message", "agent_response",
            "_score", "_explanation",
        ]].rename(columns={
            "_score": "frustration_score",
            "_explanation": "frustration_explanation",
        })

        client.datasets.create_dataset(
            name=DATASET_NAME,
            dataframe=dataset_df,
            input_keys=["user_message", "session_id", "user_id"],
            output_keys=["agent_response"],
            metadata_keys=["span_id", "frustration_score", "frustration_explanation"],
        )
        print(f"Dataset '{DATASET_NAME}' created in Phoenix ({len(dataset_df)} examples)")
    else:
        print("No frustrated spans — dataset not created")


if __name__ == "__main__":
    main()
