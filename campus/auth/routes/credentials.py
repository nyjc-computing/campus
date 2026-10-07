"""campus.auth.routes.credentials

Flask routes for credentials management.

Credential records ARE bearer credentials: a campus-provider record's
id doubles as its access token and its fields include refresh material,
so the whole blueprint requires the operator principal
(AUTH_OPERATOR_CLIENT_IDS) (#854) — previously any authenticated
principal could list every live campus token. Third-party provider
records are refused outright (invariant B1).

Authentication is handled in a global routes.before_request hook.
"""

import flask

import campus.model
from campus import flask_campus
from campus.common import schema
from campus.common.errors import FieldError, ValidationError, api_errors

from .. import authz
from ..resources import credentials as creds_resource

# Create blueprint for session management routes
bp = flask.Blueprint('credentials', __name__, url_prefix='/credentials')


def _reject_non_campus_provider(provider: str) -> None:
    """Refuse the credentials API for third-party providers.

    Campus is the sole custodian of upstream credentials (invariant B1,
    docs/auth-token-invariants.md): the credential records for
    providers like google/github/discord hold those users' upstream
    access AND refresh tokens, which must never leave Campus over this
    API. Upstream access tokens are released only through the token
    bridge (/auth/v1/broker), which enforces the client flag and scope
    ceiling (invariants C1-C3).
    """
    if provider != "campus":
        raise api_errors.ForbiddenError(
            f"Provider {provider!r} credentials are not exposed via the "
            "credentials API; upstream tokens are released only via "
            "/auth/v1/broker (docs/auth-token-invariants.md B1/C1)"
        )


@bp.get("/<provider>/")
@flask_campus.unpack_request
def get_by_token(
        *,
        provider: str,
        token_id: str | None = None,
) -> flask_campus.JsonResponse:
    """Get credentials for a specific token, or list all credentials for
    a provider.

    GET /credentials/{provider}
    Authorization: operator only (#854).

    Query Params: {
        "token_id": token_id (optional)
    }
    Returns: {
        "credentials": { ... }
    }
    """
    authz.require_operator("read credential records")
    _reject_non_campus_provider(provider)
    if token_id:
        credentials = creds_resource[provider].get(token_id)
        return credentials.to_resource(), 200
    else:
        # list all
        credentials_list = creds_resource[provider].list_all()
        return {
            "credentials": [
                cred.to_resource() for cred in credentials_list
            ]
        }, 200


@bp.delete("/<provider>/<user_id>")
@flask_campus.unpack_request
def delete_by_user(
        provider: str,
        user_id: schema.UserID,
) -> flask_campus.JsonResponse:
    """Delete credentials for a specific provider and user ID.

    DELETE /credentials/{provider}/{user_id}
    Authorization: operator only (#854).

    Returns: {
        "success": true
    }
    """
    authz.require_operator("delete credential records")
    client_id = flask.g.current_client.id
    _reject_non_campus_provider(provider)
    creds_resource[provider][user_id].delete(client_id)
    return {}, 200


@bp.get("/<provider>/<user_id>")
@flask_campus.unpack_request
def get_by_user(
        provider: str,
        user_id: schema.UserID,
        client_id: schema.CampusID | None = None,
) -> flask_campus.JsonResponse:
    """Get credentials for a specific provider and user ID.

    GET /credentials/{provider}/{user_id}
    Authorization: operator only (#854).

    Query Params: {
        "client_id": <optional_client_id>
    }
    Returns: { ... }
    """
    authz.require_operator("read credential records")
    _reject_non_campus_provider(provider)
    client_id = client_id or flask.g.current_client.id
    assert client_id  # Authorization already done by this point
    credentials = creds_resource[provider][user_id].get(client_id)
    return credentials.to_resource(), 200


@bp.patch("/<provider>/<user_id>")
@flask_campus.unpack_request
def update_credentials(
        provider: str,
        user_id: schema.UserID,
        token: dict,
) -> flask_campus.JsonResponse:
    """Update credentials for a specific provider and user ID.

    PATCH /credentials/{provider}/{user_id}
    Authorization: operator only (#854).

    Body: {
        "client_id": "client_id",
        "token": { ... }
    }
    Returns: {}
    """
    authz.require_operator("update credential records")
    _reject_non_campus_provider(provider)
    client_id = flask.g.current_client.id
    try:
        # The body arrives as a plain dict; the resource layer expects
        # an OAuthToken model. Validate via from_resource, not
        # OAuthToken(**token): token resources carry the RFC 6749
        # `scope` string (a property, not a constructor field) during
        # the #648 deprecation window, and unknown provider keys are
        # bagged into provider_fields (#650) rather than rejected.
        oauth_token = campus.model.OAuthToken.from_resource(token)
    except (TypeError, ValueError) as e:
        raise ValidationError(
            "token must be a valid token object",
            errors=[FieldError(
                field="token",
                code="INVALID_FORMAT",
                message=str(e)
            )]
        ) from e
    creds_resource[provider][user_id].update(
        client_id,
        oauth_token
    )
    return {}, 200


@bp.post("/<provider>/<user_id>")
@flask_campus.unpack_request
def new_credentials(
        provider: str,
        user_id: schema.UserID,
        scopes: list[str],
        expires_in: int,
) -> flask_campus.JsonResponse:
    """Issue new credentials for a specific provider and user ID.

    POST /credentials/{provider}/{user_id}
    Authorization: operator only (#854).

    Body: {
        "client_id": "client_id",
        "scopes": [...],
        "expires_in": 3600
    }
    Returns: {
        "credentials": { ... }
    }
    """
    authz.require_operator("issue credential records")
    _reject_non_campus_provider(provider)
    client_id = flask.g.current_client.id
    credentials = creds_resource[provider][user_id].new(
        client_id=client_id,
        scopes=scopes,
        expires_in=expires_in
    )
    return credentials.to_resource(), 201


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('credentials', __name__, url_prefix='/credentials')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/<provider>/", "get_by_token", get_by_token, methods=["GET"])
    new_bp.add_url_rule("/<provider>/<user_id>", "delete_by_user", delete_by_user, methods=["DELETE"])
    new_bp.add_url_rule("/<provider>/<user_id>", "get_by_user", get_by_user, methods=["GET"])
    new_bp.add_url_rule("/<provider>/<user_id>", "update_credentials", update_credentials, methods=["PATCH"])
    new_bp.add_url_rule("/<provider>/<user_id>", "new_credentials", new_credentials, methods=["POST"])

    return new_bp
