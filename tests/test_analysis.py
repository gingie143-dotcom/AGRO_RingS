import json
import pytest
from pydantic import ValidationError
from gateway.analysis import parse_response


def test_analysis_refusal_and_incomplete():
    assert parse_response({"status": "incomplete"})["analysis_status"] == "incomplete"
    assert (
        parse_response({"status": "completed", "output": [{"content": [{"type": "refusal"}]}]})[
            "analysis_status"
        ]
        == "refused"
    )


def test_analysis_schema_validation():
    result = {
        "conversation_summary": "Попросил информацию",
        "customer_intent": None,
        "interest_level": None,
        "objections": [],
        "important_points": [],
        "next_action": None,
        "callback_required": False,
        "callback_datetime": None,
        "transfer_to_human": False,
        "conversation_quality": None,
        "assessment_kind": "uncertain_ai_estimate",
    }

    def response(value):
        return {
            "status": "completed",
            "output": [{"content": [{"type": "output_text", "text": json.dumps(value)}]}],
        }

    assert parse_response(response(result))["analysis_status"] == "completed"
    result["interest_level"] = 101
    with pytest.raises(ValidationError):
        parse_response(response(result))
