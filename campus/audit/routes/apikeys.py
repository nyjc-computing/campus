"""campus.audit.routes.api_keys

API key management endpoints for the audit service.
"""

__all__ = [
    "create_blueprint",
]

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources

# Create blueprint for API key routes
bp = flask.Blueprint('apikeys', __name__, url_prefix='/apikeys')


@bp.post("/")
@flask_campus.unpack_request
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
        400 Bad Request on invalid input
    """
    api_key = resources.apikeys.new(
        name=name,
        owner_id=owner_id,
        scopes=",".join(scopes),
        rate_limit=rate_limit,
        expires_at=expires_at,
    )
    return api_key.to_resource(), 201


@bp.get("/")
@flask_campus.unpack_request
def list_keys(
        *,
        owner_id: schema.UserID | None = None,
        active_only: bool = True,
        limit: schema.Integer = schema.Integer(50),
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
def update(
        api_key_id: schema.CampusID,
        *,
        name: schema.CampusID | None = None,
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
    """
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
    new_bp.add_url_rule("/<api_key_id>/regenerate/", "regenerate", regenerate, methods=["POST"])

    return new_bp
