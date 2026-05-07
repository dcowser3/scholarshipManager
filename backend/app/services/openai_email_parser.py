from __future__ import annotations

import json
from decimal import Decimal
from urllib import error, request

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.core import Sport
from app.models.roster import RosterMembership
from app.services.config_values import get_config_value


class OpenAIParseError(RuntimeError):
    pass


def parse_adjustment_email_with_openai(
    db: Session,
    *,
    sport: Sport,
    email_body: str,
    roster_memberships: list[RosterMembership],
) -> dict:
    api_key = get_config_value(db, "openai.api_key")
    if not api_key:
        raise OpenAIParseError("OpenAI API key is not configured")

    payload = {
        "model": get_config_value(db, "openai.model") or settings.openai_model,
        "input": [
            {"role": "system", "content": _build_system_prompt()},
            {
                "role": "user",
                "content": _build_user_prompt(
                    sport=sport,
                    email_body=email_body,
                    roster_memberships=roster_memberships,
                ),
            },
        ],
        "temperature": 0,
        "max_output_tokens": 1400,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "email_adjustment_parse",
                "strict": True,
                "schema": _response_schema(),
            }
        },
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as caught:
        detail = caught.read().decode("utf-8", errors="replace")
        raise OpenAIParseError(
            f"OpenAI parsing request failed with {caught.code}: {detail}"
        ) from caught
    except error.URLError as caught:
        raise OpenAIParseError(f"OpenAI parsing request failed: {caught.reason}") from caught

    raw_response = json.loads(body)
    parsed_text = _extract_output_text(raw_response)
    return _extract_json_object(parsed_text)


def _build_system_prompt() -> str:
    return (
        "You parse a coach email into structured scholarship adjustment JSON. "
        "Do not guess. If the athlete or intent is ambiguous, add an issue and leave "
        "rocket_id null for that change."
    )


def _build_user_prompt(
    *,
    sport: Sport,
    email_body: str,
    roster_memberships: list[RosterMembership],
) -> str:
    roster = [
        {
            "rocket_id": membership.athlete_id,
            "full_name": f"{membership.athlete.first_name} {membership.athlete.last_name}",
        }
        for membership in roster_memberships
        if membership.athlete
    ]
    return (
        "Canonical field names: athletic_aid_total, oos_tuition, tuition, general_fee, "
        "misc_fee, room, board, books, personal_expenses, oos_resource.\n"
        "Semesters must be FALL or SPRING.\n"
        "Operation must be SET when the email means 'to $X'.\n"
        "Operation must be DELTA when the email means 'by $X', 'increase', 'decrease', "
        "'add', or 'remove'. Use negative amounts for decreases.\n\n"
        f"Sport: {sport.display_name}\n"
        f"Roster JSON: {json.dumps(roster)}\n"
        f"Email body:\n{email_body}\n"
    )


def _response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "overall_confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "issues": {"type": "array", "items": {"type": "string"}},
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "athlete_name": {"type": "string"},
                        "rocket_id": {"type": ["string", "null"]},
                        "term": {
                            "type": ["string", "null"],
                            "enum": ["FALL", "SPRING", None],
                        },
                        "field": {"type": ["string", "null"]},
                        "operation": {
                            "type": ["string", "null"],
                            "enum": ["SET", "DELTA", None],
                        },
                        "amount": {"type": ["string", "null"]},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "issue": {"type": ["string", "null"]},
                        "source_text": {"type": "string"},
                    },
                    "required": [
                        "athlete_name",
                        "rocket_id",
                        "term",
                        "field",
                        "operation",
                        "amount",
                        "confidence",
                        "issue",
                        "source_text",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "overall_confidence", "issues", "changes"],
        "additionalProperties": False,
    }


def _extract_output_text(response_payload: dict) -> str:
    output = response_payload.get("output", [])
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text", "")
                if text:
                    return text
    raise OpenAIParseError("OpenAI response did not contain output_text content")


def _extract_json_object(value: str) -> dict:
    stripped = value.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise OpenAIParseError("OpenAI response did not contain a JSON object")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise OpenAIParseError("OpenAI response JSON must be an object")
    return parsed


def decimal_string(value: str | int | float | Decimal | None) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(Decimal("0.01")))
