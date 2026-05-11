"""
Evaluate user frustration across travel-assistant traces in Phoenix.

Usage:
    poetry run python eval/evaluate_frustration.py

Connects to Phoenix at localhost:6006, fetches root LangGraph spans
(one per trace), runs a ClassificationEvaluator (GPT-4o-mini judge) to
detect user frustration, posts results as span annotations, and uploads
a dataset of frustrated interactions. Also exports raw spans and eval
results to eval/spans/ as CSV files.
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

    # Export raw spans to CSV
    spans_dir = Path(__file__).parent / "spans"
    spans_dir.mkdir(exist_ok=True)
    raw_path = spans_dir / "raw_spans.csv"
    spans_df.to_csv(raw_path)
    print(f"Exported {len(spans_df)} raw spans to {raw_path}")

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
    print("\nPosting annotations:")
    for _, row in results.iterrows():
        span_id = row["span_id"]
        score_obj = row.get("user_frustration_score") or {}
        _post_annotation(client, span_id, "user_frustration", score_obj)
        label = str(score_obj.get("label") or "ok")
        tag = "FRUSTRATED" if label == "frustrated" else "ok      "
        session = str(row.get("session_id", ""))[:35]
        print(f"  [{tag}]  {session}")

    # --- 5. Export evaluation results to CSV ----------------------------------
    results["_label"] = results["user_frustration_score"].apply(
        lambda s: (s or {}).get("label", "ok")
    )
    results["_score"] = results["user_frustration_score"].apply(
        lambda s: float((s or {}).get("score", 0.0))
    )
    results["_explanation"] = results["user_frustration_score"].apply(
        lambda s: (s or {}).get("explanation", "")
    )

    export_df = results[[
        "span_id", "session_id", "user_id",
        "user_message", "agent_response",
        "_label", "_score", "_explanation",
    ]].rename(columns={
        "_label": "frustration_label",
        "_score": "frustration_score",
        "_explanation": "frustration_explanation",
    })
    eval_path = spans_dir / "frustration_eval_results.csv"
    export_df.to_csv(eval_path, index=False)
    print(f"\nExported evaluation results to {eval_path}")

    # --- 6. Create dataset of frustrated interactions -------------------------
    frustrated = results[results["_label"] == "frustrated"].copy()
    print(f"{len(frustrated)} / {len(results)} spans classified as frustrated")

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
