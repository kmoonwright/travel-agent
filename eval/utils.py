import json

from phoenix.client import Client

PHOENIX_URL = "http://127.0.0.1:6006"
PROJECT_NAME = "travel-assistant"
EVAL_MODEL = "gpt-4o-mini"


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


def _post_annotation(client: Client, span_id: str, name: str, score_obj: dict) -> None:
    label = str(score_obj.get("label") or "")
    score = float(score_obj.get("score") or 0.0)
    explanation = str(score_obj.get("explanation") or "")
    client.spans.add_span_annotation(
        span_id=span_id,
        annotation_name=name,
        annotator_kind="LLM",
        label=label,
        score=score,
        explanation=explanation,
        metadata={"model": EVAL_MODEL},
        sync=True,
    )
