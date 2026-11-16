"""campus.auth.routes.credentials

Flask routes for credentials management.

Credential records ARE bearer credentials: a campus-provider record's
id doubles as its access token and its fields include refresh material,
so the whole blueprint requires the operator principal
(AUTH_OPERATOR_CLIENT_IDS) (#854) — previously any authenticated
principal could list every live campus token. Third-party provider
records are refused outright (invariant B1).

Since #1055 the reads are redacted by default: list and per-record
GETs return token metadata (expiry, type, scopes) but never the raw
token material, and the raw token comes back only on a per-record
?include=token opt-in (operator principal or super-admin root —
never on the list, so no principal can bulk-download live tokens).
Designated admin users join via the credentials vocabulary
(credentials:read reads, credentials:write disconnects/updates);
DELETE takes an optional ?client_id= so the operator can disconnect
an arbitrary integration's stored record, not just its own
(the client_id rides the JSON body, like the SDK's delete).

Authentication is handled in a global routes.before_request hook.
"""

import flask

import campus.flask_campus as flask_campus
import campus.model
from campus.common import schema
from campus.common.errors import FieldError, ValidationError, api_errors

from .. import authz, get_yapper
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


# Token metadata surfaced on redacted reads (#1055): expiry, type,
# and scopes identify the credential for admin views without
# releasing material. id (the access-token string itself) and
# refresh_token never appear outside a ?include=token read.
_TOKEN_METADATA_FIELDS = (
    "expires_at",
    "expires_in",
    "token_type",
    "scope",
    "refresh_token_expires_at",
)


def _credentials_view(cred, include_token: bool = False) -> dict:
    """Serialize a credential record for the current principal (#1055).

    Redacted by default: the joined token is reduced to its metadata.
    include_token=True (per-record reads only, operator/super-admin
    only — enforced by the caller) emits the full token resource for
    the rare legitimate full read.
    """
    resource = cred.to_resource()
    token = resource.get("token")
    if token is not None and not include_token:
        resource["token"] = {
            field: token[field]
            for field in _TOKEN_METADATA_FIELDS
            if field in token
        }
    return resource


def _require_token_disclosure(include: str | None) -> bool:
    """The ?include=token opt-in gate (#1055).

    Returns True when the caller explicitly asked for the raw token
    and is allowed to see it. The opt-in exists for the rare
    legitimate full read of ONE record: it is refused on the list
    route (no principal may bulk-download live tokens — the #1055
    exposure class), and to user principals however designated: raw
    token disclosure is an operator-principal power.
    """
    if include != "token":
        return False
    if authz.is_user_principal() and not authz.is_super_admin():
        raise api_errors.ForbiddenError(
            "?include=token is an operator-principal power (#1055): "
            "designated admin users read credential metadata only"
        )
    if not (authz.is_operator() or authz.is_super_admin()):
        raise api_errors.ForbiddenError(
            "?include=token requires the operator principal "
            f"({authz.OPERATOR_CLIENT_IDS_ENVVAR}) (#1055)"
        )
    return True


@bp.get("/<provider>/")
@flask_campus.unpack_request
def get_by_token(
        *,
        provider: str,
        token_id: str | None = None,
        include: str | None = None,
) -> flask_campus.JsonResponse:
    """Get campus credentials by token, or list for a provider

    Campus-provider credentials only — third-party providers are
    refused with 403 (invariant B1: upstream tokens are custodied
    by Campus and released only via the token bridge).

    GET /credentials/{provider}
    Authorization: the operator, or a designated admin user whose
    grant row and token cover credentials:read (#1055). Reads are
    redacted (#1055): token metadata only.

    Query Params: {
        "token_id": token_id (optional),
        "include": "token"  # per-record opt-in for the raw token;
                            # operator/super-admin only, NEVER honored
                            # on the list
    }
    Returns: {
        "credentials": [ ...redacted records... ]
    }
    """
    authz.require_operator(
        "read credential records",
        admin_scope=authz.CREDENTIALS_READ,
    )
    _reject_non_campus_provider(provider)
    include_token = _require_token_disclosure(include)
    if token_id:
        credentials = creds_resource[provider].get(token_id)
        return _credentials_view(credentials, include_token), 200
    else:
        # list all — always redacted: no principal may bulk-download
        # live tokens (#1055)
        credentials_list = creds_resource[provider].list_all()
        return {
            "credentials": [
                _credentials_view(cred) for cred in credentials_list
            ]
        }, 200


@bp.delete("/<provider>/<user_id>/")
@flask_campus.unpack_request
def delete_by_user(
        provider: str,
        user_id: schema.UserID,
        client_id: schema.CampusID | None = None,
) -> flask_campus.JsonResponse:
    """Disconnect a user's campus credentials

    DELETE /credentials/{provider}/{user_id}/
    Authorization: the operator, or a designated admin user whose
    grant row and token cover credentials:write (#1055).

    Body (optional): {
        "client_id": <optional_client_id>  # disconnect an arbitrary
        # integration's record for (provider, user_id); the calling
        # client's record is the default (#1055)
    }
    Returns: {}
    """
    authz.require_operator(
        "delete credential records",
        admin_scope=authz.CREDENTIALS_WRITE,
    )
    _reject_non_campus_provider(provider)
    client_id = client_id or flask.g.current_client.id
    assert client_id  # Authorization already done by this point
    creds_resource[provider][user_id].delete(client_id)
    get_yapper().emit(
        'campus.credentials.disconnect',
        {
            "provider": provider,
            "user_id": str(user_id),
            "client_id": str(client_id),
        }
    )
    return {}, 200


@bp.get("/<provider>/<user_id>/")
@flask_campus.unpack_request
def get_by_user(
        provider: str,
        user_id: schema.UserID,
        client_id: schema.CampusID | None = None,
        include: str | None = None,
) -> flask_campus.JsonResponse:
    """Get a user's campus credentials for the calling client

    GET /credentials/{provider}/{user_id}/
    Authorization: the operator, or a designated admin user whose
    grant row and token cover credentials:read (#1055). Redacted by
    default (#1055): token metadata only.

    Query Params: {
        "client_id": <optional_client_id>,
        "include": "token"  # opt-in for the raw token;
                            # operator/super-admin only
    }
    Returns: { ... }
    """
    authz.require_operator(
        "read credential records",
        admin_scope=authz.CREDENTIALS_READ,
    )
    _reject_non_campus_provider(provider)
    include_token = _require_token_disclosure(include)
    client_id = client_id or flask.g.current_client.id
    assert client_id  # Authorization already done by this point
    credentials = creds_resource[provider][user_id].get(client_id)
    return _credentials_view(credentials, include_token), 200


@bp.patch("/<provider>/<user_id>/")
@flask_campus.unpack_request
def update_credentials(
        provider: str,
        user_id: schema.UserID,
        token: dict,
) -> flask_campus.JsonResponse:
    """Replace a user's campus token

    PATCH /credentials/{provider}/{user_id}/
    Authorization: operator only (#854).

    Body: {
        "client_id": "client_id",
        "token": { ... }
    }
    Returns: {}
    """
    authz.require_operator(
        "update credential records",
        admin_scope=authz.CREDENTIALS_WRITE,
    )
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
    get_yapper().emit(
        'campus.credentials.update',
        {
            "provider": provider,
            "user_id": str(user_id),
            "client_id": str(client_id),
        }
    )
    return {}, 200


@bp.post("/<provider>/<user_id>/")
@flask_campus.unpack_request
def new_credentials(
        provider: str,
        user_id: schema.UserID,
        scopes: list[str],
        expires_in: int,
) -> flask_campus.JsonResponse:
    """Issue campus credentials for a user

    Issues a new campus token bound to the calling client (provider must be `campus`).

    POST /credentials/{provider}/{user_id}/
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
    authz.require_operator(
        "issue credential records",
        admin_scope=authz.CREDENTIALS_WRITE,
    )
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
    new_bp.add_url_rule("/<provider>/<user_id>/", "delete_by_user", delete_by_user, methods=["DELETE"])
    new_bp.add_url_rule("/<provider>/<user_id>/", "get_by_user", get_by_user, methods=["GET"])
    new_bp.add_url_rule("/<provider>/<user_id>/", "update_credentials", update_credentials, methods=["PATCH"])
    new_bp.add_url_rule("/<provider>/<user_id>/", "new_credentials", new_credentials, methods=["POST"])

    return new_bp
