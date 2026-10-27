"""campus.api.questionschemas

Registry of question types for assignments and submissions (#533).

Each entry maps a type id to a JSON Schema pair (draft 2020-12, the
house style of nyjc-computing/exam-schemas): one schema for the
question's `data`, one for a response's `response_data`, plus an
optional cross-check that sees both. Adding a question type means
registering an entry here — no core model changes.

Validation lives at this payload boundary, not in campus.model: reads
construct model objects on every fetch, so schema validation is
write-time-only (422 VALIDATION_FAILED). Stored records were validated
when written and are trusted on read.
"""

import typing
from dataclasses import dataclass

import jsonschema

import campus.model
from campus.common.errors import FieldError, ValidationError

_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"

# Type-agnostic configuration: the type itself carries the semantics.
_NO_CONFIG_SCHEMA = {
    "$schema": _SCHEMA_DRAFT,
    "type": "object",
    "additionalProperties": False,
    "properties": {},
    "description": "No type-specific configuration.",
}

_SHORT_ANSWER_RESPONSE_SCHEMA = {
    "$schema": _SCHEMA_DRAFT,
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {
        "text": {
            "type": "string",
            "maxLength": 256,
            "pattern": "^[^\r\n]*$",
            "description": "Single-line answer; at most 256 characters, "
                           "no line breaks.",
        },
    },
}

_FREE_RESPONSE_RESPONSE_SCHEMA = {
    "$schema": _SCHEMA_DRAFT,
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {
        "text": {
            "type": "string",
            "description": "Plain text; line breaks are preserved. No other "
                           "formatting — renderers must escape and never "
                           "interpret markup.",
        },
    },
}

_MULTIPLE_CHOICE_QUESTION_SCHEMA = {
    "$schema": _SCHEMA_DRAFT,
    "type": "object",
    "additionalProperties": False,
    "required": ["options"],
    "properties": {
        "options": {
            "type": "array",
            "minItems": 2,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text"],
                "properties": {
                    "id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 64,
                        "pattern": "^[A-Za-z0-9_-]+$",
                        "description": "Stable identifier minted at "
                                       "authoring time; survives reordering, "
                                       "shuffling and text edits. Builders "
                                       "must preserve it across edits and "
                                       "mint one only for new options.",
                    },
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                    },
                },
            },
            "description": "Choices in stored order; renderers may reorder "
                           "(e.g. shuffle) for display — stored order has "
                           "no answer semantics.",
        },
        "randomize": {
            "type": "boolean",
            "default": False,
            "description": "Renderer hint: present options in a per-student "
                           "shuffled order. Storage and responses are "
                           "order-independent regardless.",
        },
    },
}

_MULTIPLE_CHOICE_RESPONSE_SCHEMA = {
    "$schema": _SCHEMA_DRAFT,
    "type": "object",
    "additionalProperties": False,
    "required": ["choice"],
    "properties": {
        "choice": {
            "type": "string",
            "minLength": 1,
            "description": "The chosen option's stable id.",
        },
    },
}


def _check_multiple_choice(question_data: dict, response_data: dict) -> None:
    """Cross-check an MCQ response against its question's options.

    Raises ValueError with a message suitable for a FieldError. JSON
    Schema cannot see the question here, so this is the only place that
    can confirm the choice names a real option (and that ids/texts are
    unique — `uniqueItems` only catches exact duplicates).
    """
    options = question_data.get("options") or []
    ids = []
    texts = []
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("options must be objects with id and text")
        ids.append(option.get("id"))
        texts.append(option.get("text"))
    if len(set(ids)) != len(ids):
        raise ValueError("options contain duplicate ids")
    if len(set(texts)) != len(texts):
        raise ValueError("options contain duplicate texts")
    if response_data.get("choice") not in ids:
        raise ValueError("choice does not match any option id")


@dataclass(frozen=True)
class QuestionType:
    """A registered question type.

    Attributes:
        type_id: Registry key, stored as Question.type / Response.question_type.
        label: Human-readable name for error messages and UI pickers.
        question_schema: JSON Schema validating Question.data.
        response_schema: JSON Schema validating Response.response_data.
        validate_against_question: Optional cross-check receiving
            (question_data, response_data); raise ValueError on failure.
    """
    type_id: str
    label: str
    question_schema: dict
    response_schema: dict
    validate_against_question: (
        typing.Callable[[dict, dict], None] | None
    ) = None


REGISTRY: dict[str, QuestionType] = {
    qt.type_id: qt
    for qt in [
        QuestionType(
            type_id="short-answer",
            label="Short answer",
            question_schema=_NO_CONFIG_SCHEMA,
            response_schema=_SHORT_ANSWER_RESPONSE_SCHEMA,
        ),
        QuestionType(
            type_id="free-response",
            label="Free response",
            question_schema=_NO_CONFIG_SCHEMA,
            response_schema=_FREE_RESPONSE_RESPONSE_SCHEMA,
        ),
        QuestionType(
            type_id="multiple-choice",
            label="Multiple choice",
            question_schema=_MULTIPLE_CHOICE_QUESTION_SCHEMA,
            response_schema=_MULTIPLE_CHOICE_RESPONSE_SCHEMA,
            validate_against_question=_check_multiple_choice,
        ),
    ]
}

DEFAULT_TYPE_ID = "free-response"


def get(type_id: str) -> QuestionType | None:
    """Return the registered question type, or None if unknown."""
    return REGISTRY.get(type_id)


def questions_from_payloads(
        payloads: list[dict],
        field: str,
) -> list[campus.model.Question]:
    """Construct Question models from payload dicts and validate.

    Same contract as payloads.models_from_payloads (422 VALIDATION_FAILED
    naming `field[i]`), plus registry checks: an unknown type id or a
    `data` that fails the type's question_schema is a field error.

    Args:
        payloads: Payload dicts from the request body.
        field: Request body field name the payloads came from.

    Returns:
        Constructed Question models, in payload order.

    Raises:
        ValidationError: A payload does not match the model or its
            registered question schema.
    """
    questions: list[campus.model.Question] = []
    for i, payload in enumerate(payloads):
        try:
            question = campus.model.Question(**payload)
        except (TypeError, ValueError) as e:
            raise _payload_error(field, i, str(e)) from e

        errors = _question_errors(question, field, i)
        if errors:
            raise ValidationError(
                f"{field}[{i}] does not match the "
                f"'{question.type}' question schema",
                errors=errors,
            )
        questions.append(question)
    return questions


def responses_from_payloads(
        payloads: list[dict],
        field: str,
        questions: list[campus.model.Question] | None = None,
) -> list[campus.model.Response]:
    """Construct Response models from payload dicts and validate.

    Same contract as payloads.models_from_payloads, plus registry
    checks. When `questions` (the parent assignment's questions) is
    given and contains the answered question, ITS registered type
    governs validation and the type's cross-check runs against the
    question's data — the payload's denormalized question_type is a
    cache and a mismatch is tolerated. When the question is not found
    (unknown question_id) or its type is not registered, validation
    falls back to the payload's question_type and skips cross-checks:
    unknown question ids are deliberately not rejected, so drafts
    survive teacher edits that remove questions (stale answers surface
    at render instead — see #533).

    Args:
        payloads: Payload dicts from the request body.
        field: Request body field name the payloads came from.
        questions: Parent assignment questions for type lookup and
            cross-checks, when the assignment is at hand.

    Returns:
        Constructed Response models, in payload order.

    Raises:
        ValidationError: A payload does not match the model or the
            governing response schema.
    """
    responses: list[campus.model.Response] = []
    for i, payload in enumerate(payloads):
        try:
            response = campus.model.Response(**payload)
        except (TypeError, ValueError) as e:
            raise _payload_error(field, i, str(e)) from e

        question = _find_question(questions, response.question_id)
        question_type = None
        if question is not None:
            question_type = get(question.type)
        if question_type is None:
            question_type = get(response.question_type)
            if question_type is None:
                raise ValidationError(
                    f"{field}[{i}] does not match the "
                    f"'{response.question_type}' question schema",
                    errors=[
                        _field_error(
                            f"{field}[{i}].question_type",
                            f"unknown question type "
                            f"'{response.question_type}'; known types: "
                            f"{', '.join(sorted(REGISTRY))}",
                        )
                    ],
                )

        # Legacy payloads carry only response_text; the model mirror
        # synthesizes response_data from it, so validation always sees
        # the canonical shape. An entirely empty response normalizes to
        # {"text": ""}, which the text types accept.
        response_data = response.response_data or {
            "text": response.response_text,
        }
        errors = _schema_errors(
            response_data,
            question_type.response_schema,
            f"{field}[{i}].response_data",
        )
        if errors:
            raise ValidationError(
                f"{field}[{i}] does not match the "
                f"'{question_type.type_id}' question schema",
                errors=errors,
            )

        if question is not None and question_type.validate_against_question:
            question_data = question.data or {}
            try:
                question_type.validate_against_question(
                    question_data, response_data
                )
            except ValueError as e:
                raise ValidationError(
                    f"{field}[{i}] does not match its question's options",
                    errors=[_field_error(f"{field}[{i}]", str(e))],
                ) from e

        responses.append(response)
    return responses


def _payload_error(field: str, index: int, message: str) -> ValidationError:
    """A 422 for a payload that does not fit the model's own fields."""
    return ValidationError(
        f"{field}[{index}] does not match the model schema",
        errors=[_field_error(f"{field}[{index}]", message)],
    )


def _field_error(field_path: str, message: str) -> FieldError:
    return FieldError(
        field=field_path,
        code="INVALID_FORMAT",
        message=message,
    )


def _find_question(
        questions: list[campus.model.Question] | None,
        question_id: str,
) -> campus.model.Question | None:
    for question in questions or []:
        if question.id == question_id:
            return question
    return None


def _question_errors(
        question: campus.model.Question,
        field: str,
        index: int,
) -> list[FieldError]:
    """Registry errors for a constructed Question (unknown type, bad data)."""
    question_type = get(question.type)
    if question_type is None:
        return [
            _field_error(
                f"{field}[{index}].type",
                f"unknown question type '{question.type}'; known types: "
                f"{', '.join(sorted(REGISTRY))}",
            )
        ]
    return _schema_errors(
        question.data or {},
        question_type.question_schema,
        f"{field}[{index}].data",
    )


def _schema_errors(
        instance: typing.Any,
        schema: dict,
        field_path: str,
) -> list[FieldError]:
    """All draft 2020-12 validation failures as field errors."""
    validator = jsonschema.Draft202012Validator(schema)
    return [
        _field_error(field_path, error.message)
        for error in validator.iter_errors(instance)
    ]
