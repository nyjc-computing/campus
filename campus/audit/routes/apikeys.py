"""campus.audit.routes.api_keys

API key management endpoints for the audit service.

All routes require an authenticated audit API key with the appropriate
apikeys:* scope (#796): apikeys:read for reads, apikeys:write for
mutations. Only the operator key seeded at startup
(campus.audit.resources.apikeys.ensure_operator_key) holds apikeys:*
scopes, so key management cannot be hijacked by a scoped producer key.
"""

__all__ = [
    "create_blueprint",
]

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import FieldError, ValidationError, api_errors

from .. import decorators, resources
from ..helpers import audit_events

# Create blueprint for API key routes
bp = flask.Blueprint('apikeys', __name__, url_prefix='/apikeys')


def _validate_non_empty_str(
        field_errors: list[FieldError],
        field: str,
        value: object,
) -> None:
    """Record a field error if value is not a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        field_errors.append(FieldError(
            field=field,
            code="EMPTY" if value == "" else "INVALID_TYPE",
            message=f"{field} must be a non-empty string"
        ))


def _validate_scopes_field(
        field_errors: list[FieldError],
        scopes: object,
) -> None:
    """Record a field error unless scopes is a non-empty list of
    non-empty strings."""
    if not isinstance(scopes, list):
        field_errors.append(FieldError(
            field="scopes",
            code="INVALID_TYPE",
            message="scopes must be a list of scope strings"
        ))
        return
    if not scopes:
        field_errors.append(FieldError(
            field="scopes",
            code="EMPTY",
            message="scopes must contain at least one scope"
        ))
        return
    for scope in scopes:
        if not isinstance(scope, str) or not scope.strip():
            field_errors.append(FieldError(
                field="scopes",
                code="INVALID_TYPE",
                message="scopes must be a list of non-empty strings"
            ))
            return


def _validate_rate_limit_field(
        field_errors: list[FieldError],
        rate_limit: object,
) -> None:
    """Record a field error unless rate_limit is an integer or None."""
    if rate_limit is None:
        return
    if isinstance(rate_limit, bool) or not isinstance(rate_limit, int):
        field_errors.append(FieldError(
            field="rate_limit",
            code="INVALID_TYPE",
            message="rate_limit must be an integer or null"
        ))


@bp.post("/")
@flask_campus.unpack_request
@audit_events.audit_event("audit.apikeys.new")
@decorators.require_scopes("apikeys:write")
def new(
        *,
        name: str,
        owner_id: schema.UserID,
        scopes: list[schema.String],
        rate_limit: schema.Integer | None = None,
        expires_at: schema.DateTime | None = None,
) -> flask_campus.JsonResponse:
    """Create a new API key.

    Request body:
    {
      "name": "string",
      "owner_id": "string",
      "scopes": ["scope1", "scope2"],  // optional
      "rate_limit": 100,  // optional, requests per minute
      "expires_at": "ISO 8601"  // optional
    }

    Returns:
        201 Created with the API key (only shown once) and key details
        422 Unprocessable Entity on invalid input
    """
    field_errors: list[FieldError] = []
    _validate_non_empty_str(field_errors, "name", name)
    _validate_non_empty_str(field_errors, "owner_id", owner_id)
    _validate_scopes_field(field_errors, scopes)
    _validate_rate_limit_field(field_errors, rate_limit)
    if field_errors:
        raise ValidationError(
            message="One or more fields are invalid",
            errors=field_errors
        )
    api_key, apikey_value = resources.apikeys.new(
        name=name,
        owner_id=owner_id,
        scopes=",".join(scopes),
        rate_limit=rate_limit,
        expires_at=expires_at,
    )
    record = api_key.to_resource()
    record["api_key"] = apikey_value
    return record, 201


DEFAULT_LIST_LIMIT = schema.Integer(50)


@bp.get("/")
@flask_campus.unpack_request
@decorators.require_scopes("apikeys:read")
def list_keys(
        *,
        owner_id: schema.UserID | None = None,
        active_only: bool = True,
        limit: schema.Integer = DEFAULT_LIST_LIMIT,
) -> flask_campus.JsonResponse:
    """List API keys with optional filtering.

    Query params:
        owner_id: Filter by owner ID (optional)
        active_only: Only show active (non-expired, non-revoked) keys (default: true)
        limit: int, default 50

    Returns:
        List of API key summaries (excluding key_hash)
    """
    keys = resources.apikeys.list_keys(
        owner_id=owner_id,
        active_only=active_only,
        limit=limit,
    )
    return {
        "api_keys": [k.to_resource() for k in keys],
        "count": len(keys)
    }, 200


@bp.get("/<api_key_id>/")
@decorators.require_scopes("apikeys:read")
def get(
        api_key_id: schema.CampusID
) -> flask_campus.JsonResponse:
    """Get a specific API key by ID.

    Args:
        api_key_id: The API key identifier

    Returns:
        Full API key details (excluding key_hash)
    """
    api_key = resources.apikeys[api_key_id].get()
    if api_key is None:
        raise api_errors.NotFoundError(
            f"API key {api_key_id} not found"
        )
    return api_key.to_resource(), 200


@bp.patch("/<api_key_id>/")
@flask_campus.unpack_request
@audit_events.audit_event("audit.apikeys.update")
@decorators.require_scopes("apikeys:write")
def update(
        api_key_id: schema.CampusID,
        *,
        name: schema.String | None = None,
        scopes: list[schema.String] | None = None,
        rate_limit: schema.Integer | None = None,
) -> flask_campus.JsonResponse:
    """Update mutable fields of an API key.

    Only name, scopes, and rate_limit can be updated.
    Use DELETE to revoke an API key.

    Args:
        api_key_id: The API key identifier

    Request body:
    {
      "name": "new name",  // optional
      "scopes": ["scope1", "scope2"],  // optional
      "rate_limit": 200  // optional
    }

    Returns:
        200 OK with updated API key details
        404 Not Found if API key doesn't exist
        422 Unprocessable Entity on invalid input
    """
    field_errors: list[FieldError] = []
    if name is not None:
        _validate_non_empty_str(field_errors, "name", name)
    if scopes is not None:
        _validate_scopes_field(field_errors, scopes)
    if rate_limit is not None:
        _validate_rate_limit_field(field_errors, rate_limit)
    if field_errors:
        raise ValidationError(
            message="One or more fields are invalid",
            errors=field_errors
        )

    updates = {}
    if name is not None:
        updates["name"] = name
    if scopes is not None:
        updates["scopes"] = scopes
    if rate_limit is not None:
        updates["rate_limit"] = rate_limit

    if not updates:
        raise api_errors.InvalidRequestError(
            "No mutable fields provided for update"
        )
    resources.apikeys[api_key_id].update(**updates)
    api_key = resources.apikeys[api_key_id].get()
    if not api_key:
        raise api_errors.NotFoundError(
            f"API key {api_key_id} not found after update"
        ) from None
    return api_key.to_resource(), 200

@bp.delete("/<api_key_id>/")
@audit_events.audit_event("audit.apikeys.revoke")
@decorators.require_scopes("apikeys:write")
def revoke(
        api_key_id: schema.CampusID
) -> flask_campus.JsonResponse:
    """Revoke an API key.

    This marks the API key as revoked. It will no longer work for
    authentication, but the record is kept for audit purposes.

    Args:
        api_key_id: The API key identifier

    Returns:
        204 No Content on success
        404 Not Found if API key doesn't exist
    """
    success = resources.apikeys[api_key_id].revoke()
    if not success:
        raise api_errors.NotFoundError(
            f"API key {api_key_id} not found"
        )
    return {}, 204


@bp.post("/<api_key_id>/regenerate")
@audit_events.audit_event("audit.apikeys.regenerate")
@decorators.require_scopes("apikeys:write")
def regenerate(
        api_key_id: schema.CampusID
) -> flask_campus.JsonResponse:
    """Regenerate an API key with a new value.

    Creates a new plaintext API key value while keeping the same ID.
    The old key will no longer work after regeneration. The new key
    is returned in the response and will not be shown again.

    Args:
        api_key_id: The API key identifier

    Returns:
        200 OK with the new API key (shown only once) and updated details
        404 Not Found if API key doesn't exist
    """
    api_key = resources.apikeys[api_key_id].regenerate()
    if api_key is None:
        raise api_errors.NotFoundError(
            f"API key {api_key_id} not found"
        )
    return {"key": api_key}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('apikeys', __name__, url_prefix='/apikeys')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "create", new, methods=["POST"])
    new_bp.add_url_rule("/", "list", list_keys, methods=["GET"])
    new_bp.add_url_rule("/<api_key_id>/", "get", get, methods=["GET"])
    new_bp.add_url_rule("/<api_key_id>/", "update", update, methods=["PATCH"])
    new_bp.add_url_rule("/<api_key_id>/", "revoke", revoke, methods=["DELETE"])
    new_bp.add_url_rule("/<api_key_id>/regenerate", "regenerate", regenerate, methods=["POST"])

    return new_bp
