"""campus.api.payloads

Helpers for constructing model instances from request payload dicts.

Nested list fields in request bodies (questions, classroom_links,
responses, feedback) arrive as plain dicts, and the model dataclasses
are the canonical payload shape: unknown, missing or malformed fields
raise TypeError/ValueError from the constructor. This module converts
those failures into a 422 ValidationError that names the offending
payload item, instead of surfacing an unhandled 500 (#328).
"""

from typing import TypeVar

from campus.common.errors import FieldError, ValidationError

M = TypeVar("M")


def models_from_payloads(
        model_cls: type[M],
        payloads: list[dict],
        field: str,
) -> list[M]:
    """Construct model instances from request payload dicts.

    Args:
        model_cls: Model dataclass to construct, e.g. campus.model.Question.
        payloads: Payload dicts from the request body.
        field: Request body field name the payloads came from; used to
            identify the offending item in validation errors.

    Returns:
        Constructed model instances, in payload order.

    Raises:
        ValidationError: A payload does not match the model's fields.
    """
    models: list[M] = []
    for i, payload in enumerate(payloads):
        try:
            models.append(model_cls(**payload))
        except (TypeError, ValueError) as e:
            raise ValidationError(
                f"{field}[{i}] does not match the {model_cls.__name__} schema",
                errors=[
                    FieldError(
                        field=f"{field}[{i}]",
                        code="INVALID_FORMAT",
                        message=str(e),
                    )
                ],
            ) from e
    return models
