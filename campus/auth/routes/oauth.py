"""campus.auth.routes.oauth

Flask routes for OAuth 2.0 Device Authorization Flow (RFC 8628) and
token grants (RFC 6749: device_code, refresh_token, client_credentials)
plus token revocation (RFC 7009).

These routes handle device authorization for CLI and other device applications.

These routes do NOT require authentication - they are publicly accessible
for the device authorization flow to work.
"""

import flask

import campus.config
import campus.model
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors, token_errors
from campus.common.utils import secret, url

from .. import get_yapper, scopes
from ..resources import app_credentials
from ..resources import client as client_resource
from ..resources import credentials as credentials_resource
from ..resources import device_code as device_code_resource

# Create blueprint for OAuth routes
bp = flask.Blueprint('oauth', __name__, url_prefix='/oauth')

# Default scopes for CLI clients (the seeded public client's allowlist)
DEFAULT_CLI_SCOPES = campus.config.DEFAULT_CLI_SCOPES


def _get_oauth_payload() -> dict:
    """Get request payload for OAuth endpoints.

    OAuth 2.0 spec requires endpoints to accept application/x-www-form-urlencoded.
    This function accepts both JSON and form-encoded data for compatibility.
    """
    if flask.request.is_json:
        data = flask.request.get_json(silent=True)
        if data is None:
            raise api_errors.InvalidRequestError(
                message="Malformed JSON payload",
                error_code="MALFORMED_REQUEST"
            )
        return data
    else:
        # Fall back to form data (OAuth 2.0 standard)
        # Ensure all values are strings (form data can sometimes return bytes)
        return {k: v if isinstance(v, str) else str(v) for k, v in flask.request.form.items()}


def unpack_oauth_request(func):
    """Decorator that unpacks Flask request for OAuth endpoints.

    Accepts both JSON and form-encoded data per OAuth 2.0 specification.
    """
    from functools import wraps

    @wraps(func)
    def wrapper(**kwargs):
        request_data = _get_oauth_payload()
        return flask_campus.unpack_into(func, **kwargs, **request_data)

    return wrapper


@bp.post("/device_authorize")
@unpack_oauth_request
def device_authorize(
        client_id: schema.CampusID,
        scope: str | None = None,
) -> flask_campus.JsonResponse:
    """Request a device code for OAuth 2.0 Device Authorization Flow.

    POST /oauth/device_authorize
    Body: {
        "client_id": "guest",
        "scope": "read write"  # Optional
    }
    Returns: {
        "device_code": "...",
        "user_code": "ABCD-1234",
        "verification_uri": "https://auth.campus.nyjc.app/device",
        "verification_uri_complete": "https://auth.campus.nyjc.app/device?user_code=ABCD-1234",
        "expires_in": 600,
        "interval": 5
    }

    An absent or empty scope defaults to the standard CLI scope set
    (invariant A1: the default is still validated against the client's
    allowlist). Callers such as campus-cli pass --scope through here
    (#865); the requested scopes must lie within the client's
    registered allowlist or the request is rejected with invalid_scope.

    Reference: https://datatracker.ietf.org/doc/html/rfc8628#section-3.1
    """
    # Validate the client
    # All clients (public or confidential) must exist in the database
    try:
        client = client_resource[client_id].get()
        # Verify public client configuration
        if client.is_public and client.secret_hash:
            raise token_errors.InvalidClientError(
                "Invalid client configuration - public client should not have a secret"
            )
    except api_errors.NotFoundError:
        raise token_errors.InvalidClientError(
            "Invalid client_id"
        ) from None

    # Fail-closed scope allowlist (invariant A7,
    # docs/auth-token-invariants.md): a device code may only carry
    # scopes within the client's registered allowlist — including the
    # default CLI set when no scope was requested.
    requested_scopes = scopes.validate_for_client(
        client.allowed_scopes,
        scope if scope else DEFAULT_CLI_SCOPES,
    )

    # Create device code
    device_code = device_code_resource.create(
        client_id=client_id,
        scopes=requested_scopes,
    )

    # Build verification URIs from the canonical public origin
    # Note: endpoint needs 'auth.' prefix since oauth blueprint is registered under auth blueprint
    verification_uri = url.full_url_for(
        "auth.oauth.device_verification",
    )
    verification_uri_complete = url.full_url_for(
        "auth.oauth.device_verification",
        user_code=device_code.user_code
    )

    get_yapper().emit('campus.oauth.device_authorize', {
        "client_id": str(client_id),
        "device_code_id": str(device_code.id),
    })

    # Build response with explicit type conversion to avoid JSON serialization issues
    response = {
        "device_code": str(device_code.device_code),
        "user_code": str(device_code.user_code),
        "verification_uri": str(verification_uri),
        "verification_uri_complete": str(verification_uri_complete),
        "expires_in": int(campus.config.DEFAULT_DEVICE_CODE_EXPIRY_SECONDS),
        "interval": int(device_code.interval),
    }

    # Log types for debugging (remove after fixing)
    import logging
    logger = logging.getLogger(__name__)
    for k, v in response.items():
        logger.debug(f"Response field '{k}': type={type(v).__name__}, value={v!r}")
        if isinstance(v, bytes):
            logger.error(f"Response field '{k}' is bytes, converting to str")
            response[k] = v.decode('utf-8') if isinstance(v, bytes) else str(v)

    return response, 200


@bp.post("/token")
@unpack_oauth_request
def token(
        grant_type: str,
        client_id: schema.CampusID,
        client_secret: str | None = None,
        device_code: str | None = None,
        code: str | None = None,
        redirect_uri: str | None = None,
        refresh_token: str | None = None,
        scope: str | None = None,
) -> flask_campus.JsonResponse:
    """Exchange an authorization grant for an access token.

    Supports multiple grant types:
    - urn:ietf:params:oauth:grant-type:device_code (RFC 8628)
    - authorization_code (RFC 6749)
    - refresh_token (RFC 6749)
    - client_credentials (RFC 6749 section 4.4)

    POST /oauth/token
    Body (device code): {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": "campus-cli",
        "device_code": "..."
    }
    Body (authorization code): {
        "grant_type": "authorization_code",
        "client_id": "campus-cli",
        "code": "authorization_code",
        "redirect_uri": "https://..."
    }
    Body (refresh token): {
        "grant_type": "refresh_token",
        "client_id": "campus-cli",
        "refresh_token": "..."
    }
    Body (client credentials): {
        "grant_type": "client_credentials",
        "client_id": "uid-client-...",
        "client_secret": "..."
    }
    Returns: {
        "access_token": "...",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "...",  (never present for client_credentials)
        "scope": "read write"
    }
    """
    # Validate the client
    # All clients (public or confidential) must exist in the database
    try:
        client = client_resource[client_id].get()
        # Verify public client configuration
        if client.is_public and client.secret_hash:
            raise token_errors.InvalidClientError(
                "Invalid client configuration - public client should not have a secret"
            )
    except api_errors.NotFoundError:
        raise token_errors.InvalidClientError(
            "Invalid client_id"
        ) from None

    # Route to appropriate handler based on grant_type
    if grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        return _handle_device_code_grant(client_id, device_code)
    elif grant_type == "authorization_code":
        return _handle_authorization_code_grant(client_id, code, redirect_uri)
    elif grant_type == "refresh_token":
        return _handle_refresh_token_grant(client_id, refresh_token)
    elif grant_type == "client_credentials":
        return _handle_client_credentials_grant(client, client_secret, scope)
    else:
        raise token_errors.UnsupportedGrantTypeError(
            f"Unsupported grant_type: {grant_type}"
        )


def _handle_client_credentials_grant(
        client: campus.model.Client,
        client_secret: str | None,
        scope: str | None,
) -> flask_campus.JsonResponse:
    """Handle the client_credentials grant type (RFC 6749 section 4.4).

    Authenticates a confidential client by secret and issues (or
    reuses, see AppCredentialsResource.issue) an app-scoped token that
    resolves to the client with no user identity. Scopes follow the
    fail-closed allowlist (invariant A1): a scope parameter must be
    within the client's registered allowed_scopes, and an absent scope
    parameter defaults to the full allowlist. No refresh token is
    issued (RFC 6749 section 4.4.3); expiry is handled by re-running
    the grant.
    """
    # RFC 6749 section 4.4.2: the client credentials grant requires
    # client authentication, which public clients cannot perform
    if client.is_public:
        raise token_errors.InvalidClientError(
            "Public clients cannot use the client_credentials grant type"
        )
    if not client_secret:
        raise token_errors.InvalidRequestError(
            "client_secret is required for client_credentials grant type"
        )
    if not client_resource.is_valid_credentials(client.id, client_secret):
        raise token_errors.InvalidClientError(
            "Invalid client credentials"
        )

    granted = (
        list(client.allowed_scopes) if scope is None
        else scopes.validate_for_client(client.allowed_scopes, scope)
    )

    token = app_credentials.issue(str(client.id), granted)

    get_yapper().emit('campus.oauth.token', {
        "grant_type": "client_credentials",
        "client_id": str(client.id),
    })

    # expires_in reports the token's remaining lifetime, which is the
    # full grant lifetime on a fresh issue but shorter on reuse
    remaining = int(
        (token.expires_at.to_datetime()
         - schema.DateTime.utcnow().to_datetime()).total_seconds()
    )

    return {
        "access_token": token.id,
        "token_type": "Bearer",
        "expires_in": remaining,
        "scope": token.scope,
    }, 200


def _handle_device_code_grant(
        client_id: schema.CampusID,
        device_code: str | None,
) -> flask_campus.JsonResponse:
    """Handle the device_code grant type."""
    if not device_code:
        raise token_errors.InvalidRequestError(
            "device_code is required for device_code grant type"
        )

    # The state read above is check-then-act, but single-use is now
    # enforced atomically (#356): the "authorized" branch claims the
    # code by deleting it BEFORE minting, and delete_by_id is
    # rowcount-guarded in every storage backend. Two concurrent polls
    # that both observe "authorized" cannot both claim the code — the
    # loser gets InvalidGrantError. A mid-flight flip to "denied" or
    # "expired" cannot yield a token either: nothing writes "denied"
    # today, and expiry is re-checked inside get_by_device_code. The
    # remaining tradeoff is documented in the "authorized" branch:
    # once claimed, a storage failure before token issuance consumes
    # the code and the client must restart the flow.
    try:
        dc = device_code_resource.get_by_device_code(device_code)
    except api_errors.NotFoundError:
        raise token_errors.InvalidGrantError(
            "Invalid or expired device code"
        ) from None
    except api_errors.InvalidRequestError:
        # Device code has expired
        raise token_errors.ExpiredTokenError(
            "The device code has expired"
        ) from None

    # Check the state of the device code
    if dc.state == "pending":
        # User hasn't completed auth yet. This is the RFC 8628 §3.5
        # polling loop, so the advertised interval is enforced
        # server-side (#355): the first poll is free (last_polled_at
        # is unset, and clients may poll immediately after receiving
        # the code), and consecutive allowed polls must be at least
        # interval apart. Rejected polls do not refresh the timestamp,
        # so a hammering client costs a read and a comparison.
        # Terminal states below are not throttled: their polls don't
        # loop, and the claim in the "authorized" branch serializes
        # them (#356).
        now = schema.DateTime.utcnow()
        if dc.last_polled_at is not None:
            elapsed = (
                now.to_datetime() - dc.last_polled_at.to_datetime()
            ).total_seconds()
            if elapsed < dc.interval:
                raise token_errors.SlowDownError(
                    f"Polling too frequently; wait {dc.interval} "
                    "seconds between polls"
                )
        try:
            device_code_resource.update(dc.id, last_polled_at=now)
        except api_errors.NotFoundError:
            # Consumed between the read above and this write; the
            # claim in the "authorized" branch is the atomic gate
            # (#356).
            raise token_errors.InvalidGrantError(
                "Invalid or expired device code"
            ) from None
        raise token_errors.AuthorizationPendingError(
            "Authorization pending"
        )
    elif dc.state == "denied":
        # User denied the authorization
        raise token_errors.AccessDeniedError(
            "The user denied the authorization request"
        )
    elif dc.state == "expired":
        # Device code has expired
        raise token_errors.ExpiredTokenError(
            "The device code has expired"
        )
    elif dc.state == "authorized":
        # User has authorized - create credentials
        if not dc.user_id:
            raise api_errors.InternalError(
                "Device code is authorized but has no user_id"
            )

        # Re-validate the device code's scopes against the client's
        # current allowlist: it may have narrowed since the device was
        # authorized (invariant A7, docs/auth-token-invariants.md).
        client = client_resource[client_id].get()
        scopes.validate_for_client(client.allowed_scopes, dc.scopes)

        # Create OAuth token
        access_token = secret.generate_access_token()
        refresh_tok = secret.generate_access_code()

        # Calculate expiry
        created_at = schema.DateTime.utcnow()
        expires_in = campus.config.DEFAULT_TOKEN_EXPIRY_DAYS * 24 * 60 * 60

        # Create OAuthToken model
        oauth_token = campus.model.OAuthToken(
            id=access_token,
            created_at=created_at,
            expires_in=expires_in,
            refresh_token=refresh_tok,
            scopes=dc.scopes,
        )

        # Claim the code atomically BEFORE any write: deletion is
        # rowcount-guarded, so a concurrent poll that also observed
        # "authorized" loses the claim here (#356). From this point
        # the code is consumed; a storage failure before token
        # issuance leaves it claimed and the client restarts the flow.
        if not device_code_resource.claim(dc.id):
            raise token_errors.InvalidGrantError(
                "Device code already used or expired"
            )

        try:
            # Store credentials using the resource
            credentials_resource["campus"][dc.user_id].update(
                client_id=str(client_id),
                token=oauth_token,
            )
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e

        get_yapper().emit('campus.oauth.token', {
            "grant_type": "device_code",
            "client_id": str(client_id),
            "user_id": str(dc.user_id),
        })

        # Return token response. user_id is echoed (#837) like the
        # authorization-code grant does from the session: public clients
        # have no secret and no other way to learn who authorized them,
        # and the CLI needs it to create its login-session record.
        # RFC 8628 §3.5 permits additional response parameters.
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": campus.config.DEFAULT_TOKEN_EXPIRY_DAYS * 24 * 60 * 60,
            "refresh_token": refresh_tok,
            "scope": " ".join(dc.scopes),
            "user_id": str(dc.user_id),
        }, 200
    else:
        raise api_errors.InternalError(
            f"Invalid device code state: {dc.state}"
        )


def _handle_authorization_code_grant(
        client_id: schema.CampusID,
        code: str | None,
        redirect_uri: str | None,
) -> flask_campus.JsonResponse:
    """Handle the authorization_code grant type."""
    if not code:
        raise token_errors.InvalidRequestError(
            "code is required for authorization_code grant type"
        )

    # This is handled by the existing session endpoint
    # For now, return an error
    raise token_errors.UnsupportedGrantTypeError(
        "authorization_code grant is handled by /sessions endpoint"
    )


def _handle_refresh_token_grant(
        client_id: schema.CampusID,
        refresh_token: str | None,
) -> flask_campus.JsonResponse:
    """Handle the refresh_token grant type (RFC 6749 section 6).

    Resolves the credential by refresh token value, verifies it belongs
    to the requesting client, and issues a rotated token pair with the
    originally granted scopes. The credential update deletes the old
    token record, so the presented refresh token (and its access token)
    are single-use.
    """
    if not refresh_token:
        raise token_errors.InvalidRequestError(
            "refresh_token is required for refresh_token grant type"
        )

    try:
        credentials = credentials_resource["campus"].get_by_refresh_token(
            refresh_token
        )
    except api_errors.NotFoundError:
        raise token_errors.InvalidGrantError(
            "Invalid or expired refresh token"
        ) from None

    # The refresh token must belong to the client presenting it
    if credentials.client_id != str(client_id):
        raise token_errors.InvalidGrantError(
            "Invalid or expired refresh token"
        )

    token = credentials.token
    assert token is not None  # get_by_refresh_token always loads it

    # Refresh tokens carry their own lifetime when set; the access
    # token's expiry does not limit the refresh grant
    now = schema.DateTime.utcnow().to_timestamp()
    if (token.refresh_token_expires_at is not None
            and token.refresh_token_expires_at.to_timestamp() < now):
        raise token_errors.InvalidGrantError(
            "Invalid or expired refresh token"
        )

    # Issue a rotated token pair: new access token and new refresh token
    access_token = secret.generate_access_token()
    new_refresh_token = secret.generate_access_code()
    created_at = schema.DateTime.utcnow()
    expires_in = campus.config.DEFAULT_TOKEN_EXPIRY_DAYS * 24 * 60 * 60
    oauth_token = campus.model.OAuthToken(
        id=access_token,
        created_at=created_at,
        expires_in=expires_in,
        refresh_token=new_refresh_token,
        scopes=token.scopes,
    )

    try:
        credentials_resource["campus"][credentials.user_id].update(
            client_id=str(client_id),
            token=oauth_token,
        )
    except Exception as e:
        raise api_errors.InternalError.from_exception(e) from e

    get_yapper().emit('campus.oauth.token', {
        "grant_type": "refresh_token",
        "client_id": str(client_id),
        "user_id": str(credentials.user_id),
    })

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": new_refresh_token,
        "scope": " ".join(token.scopes),
    }, 200


@bp.post("/revoke")
@unpack_oauth_request
def revoke(
        token: str | None = None,
        client_id: schema.CampusID = None,  # pyright: ignore[reportArgumentType]
        token_type_hint: str | None = None,
) -> flask_campus.JsonResponse:
    """Revoke an access or refresh token (RFC 7009).

    POST /oauth/revoke
    Body: {
        "token": "...",
        "token_type_hint": "access_token" | "refresh_token"  (optional)
        "client_id": "campus-cli"
    }
    Returns: {} with 200

    Per RFC 7009 section 2.2, the response is 200 regardless of
    whether the token was found, already revoked, or belongs to
    another client — the endpoint does not confirm token validity to
    untrusted callers. A missing token is rejected with 400
    invalid_request (section 2.1).

    client_id carries a None default purely to keep it out of the
    required-parameters 422 path: a request without it fails client
    validation below with 400 invalid_client, which is also what the
    token endpoint does for an unknown client_id.
    """
    if not token:
        raise token_errors.InvalidRequestError(
            "token is required for revocation"
        )

    # Validate the client, like the token endpoint
    try:
        client_resource[client_id].get()
    except api_errors.NotFoundError:
        raise token_errors.InvalidClientError(
            "Invalid client_id"
        ) from None

    credentials_resource["campus"].revoke(
        token=token,
        client_id=str(client_id),
        token_type_hint=token_type_hint,
    )

    get_yapper().emit('campus.oauth.revoke', {
        "client_id": str(client_id),
    })

    return {}, 200


@bp.get("/device")
@bp.get("/device/<user_code>")
@bp.post("/device")
def device_verification(user_code: str | None = None):
    """Device code verification page for users to enter their user code.

    This is a web page that users visit to complete the device authorization
    flow. They enter the user code displayed by their CLI application.

    GET /device - Shows the entry form
    GET /device/<user_code> - Pre-fills the user code
    GET /device?status=success - Shows success state (for no-JS fallback)
    GET /device?status=error&error_code=expired - Shows error state (for no-JS fallback)
    POST /device - Handles form submission for non-JS clients
    """
    import html
    import re

    from flask import redirect, render_template_string, request, session, url_for

    # Accept the user code from both the path and the query string:
    # verification_uri_complete is "/device?user_code=XXXX-XXXX", and the
    # form should pre-fill it. Query values are format-checked before
    # being interpolated anywhere (the path param already carried the
    # same risk; this keeps the new surface no wider). The code is
    # pre-filled but NEVER auto-submitted (#852): the user must see which
    # account is authorizing and click Authorize themselves.
    if not user_code:
        query_user_code = request.args.get('user_code', '')
        if re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", query_user_code):
            user_code = query_user_code

    # Check if user is authenticated (for both GET and POST)
    # User must be logged in to authorize a device code
    user_id = session.get('user_id')
    if not user_id:
        # User not logged in - redirect to Google OAuth login
        # After login, they'll return to this page to authorize the device
        login_callback = url.full_url_for('auth.oauth.device_verification')
        if user_code:
            login_callback += f"/{user_code}"
        oauth_authorize_url = url.full_url_for(
            'auth.google.authorize',
            target=login_callback
        )
        return flask.redirect(oauth_authorize_url)

    # The browser's SSO session silently decides who authorizes the device,
    # so the page must name that account (#852). The escape hatch routes
    # through the browser-session logout and back to this page (code
    # pre-filled), forcing the Google account chooser on the next login.
    device_path = (
        url_for('auth.oauth.device_verification', user_code=user_code)
        if user_code
        else url_for('auth.oauth.device_verification')
    )
    logout_url = url.add_query(
        '/auth/v1/logout', post_logout_redirect_uri=device_path
    )

    # Handle POST for non-JS fallback
    if request.method == "POST":
        user_code_form = request.form.get('user_code', '').strip().upper()
        redirect_url = request.form.get(
            'redirect_url',
            url.full_url_for('auth.oauth.device_verification')
        )

        # Validate user code format
        if not user_code_form or len(user_code_form) != 9 or user_code_form[4] != '-':
            return redirect(f"{redirect_url}?status=error&error_code=invalid_code")

        # Try to authorize the device code
        try:
            dc = device_code_resource.get_by_user_code(user_code_form)
            if dc.state != "pending":
                error_code = "expired" if dc.state == "expired" else "already_used"
                return redirect(f"{redirect_url}?status=error&error_code={error_code}")

            device_code_resource.update(dc.id, user_id=str(user_id), state="authorized")
            get_yapper().emit('campus.oauth.device_authorize_submit', {
                "device_code_id": str(dc.id),
                "user_id": str(user_id),
            })
            return redirect(f"{redirect_url}?status=success")
        except api_errors.NotFoundError:
            return redirect(f"{redirect_url}?status=error&error_code=invalid_code")
        except Exception:
            return redirect(f"{redirect_url}?status=error&error_code=unknown")

    # Check for query parameters for non-JS redirect states
    status = request.args.get('status')
    error_code = request.args.get('error_code')

    # Error messages for no-JS fallback (must match JavaScript error_messages)
    error_messages = {
        'invalid_code': 'The user code you entered is invalid. Please check and try again.',
        'expired': 'This user code has expired. Please restart the authentication process on your CLI application to get a new code.',
        'already_used': 'This user code has already been used. Please restart the authentication process on your CLI application to get a new code.',
        'denied': 'The authorization was denied. If you did not intend to deny access, you can restart the process on your CLI application.',
        'not_logged_in': 'You must be logged in to authorize a device. Please log in first.',
        'network_error': 'Network error. Please check your connection and try again.',
        'unknown': 'An unexpected error occurred. Please try again.'
    }

    # Escape user_code for safe HTML attribute use
    safe_user_code = html.escape(user_code) if user_code else None

    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Campus - Device Authorization</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                padding: 40px;
                max-width: 480px;
                width: 100%;
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
                font-size: 24px;
            }
            .subtitle {
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                color: #333;
                font-weight: 600;
                margin-bottom: 8px;
                font-size: 14px;
            }
            .user-code-input {
                width: 100%;
                padding: 16px;
                font-size: 24px;
                font-family: 'Courier New', monospace;
                font-weight: bold;
                letter-spacing: 4px;
                text-align: center;
                text-transform: uppercase;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                transition: all 0.3s;
            }
            .user-code-input:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            .btn {
                width: 100%;
                padding: 16px;
                font-size: 16px;
                font-weight: 600;
                color: white;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border: none;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s;
            }
            .btn:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
            }
            .btn:active:not(:disabled) {
                transform: translateY(0);
            }
            .btn:disabled {
                opacity: 0.7;
                cursor: not-allowed;
            }
            .btn-secondary {
                background: #6c757d;
                margin-top: 10px;
            }
            .alert {
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-size: 14px;
                display: none;
            }
            .alert.error {
                background: #fee;
                color: #c33;
                border-left: 4px solid #c33;
            }
            .alert.success {
                background: #efe;
                color: #3c3;
                border-left: 4px solid #3c3;
            }
            .alert.show {
                display: block;
            }
            .instructions {
                background: #f5f5f5;
                padding: 16px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-size: 13px;
                color: #555;
                line-height: 1.6;
            }
            .instructions code {
                background: #e0e0e0;
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
            }
            .identity {
                background: #f0f4ff;
                border: 1px solid #d5dcf5;
                border-radius: 8px;
                padding: 10px 14px;
                margin-bottom: 20px;
                font-size: 13px;
                color: #333;
                text-align: center;
                line-height: 1.6;
            }
            .identity a {
                color: #667eea;
            }
            .spinner {
                display: inline-block;
                width: 16px;
                height: 16px;
                border: 2px solid #f3f3f3;
                border-top: 2px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-left: 10px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .success-icon {
                width: 64px;
                height: 64px;
                margin: 0 auto 20px;
                background: #4caf50;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .success-icon::after {
                content: '';
                width: 32px;
                height: 16px;
                border-left: 4px solid white;
                border-bottom: 4px solid white;
                transform: rotate(-45deg);
                margin-bottom: 6px;
            }
            .error-icon {
                width: 64px;
                height: 64px;
                margin: 0 auto 20px;
                background: #f44336;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .error-icon::after {
                content: '!';
                color: white;
                font-size: 32px;
                font-weight: bold;
            }
            .countdown {
                text-align: center;
                color: #666;
                font-size: 13px;
                margin-top: 16px;
            }
            /* Success/Error state views */
            .state-view {
                text-align: center;
            }
            .state-view h2 {
                margin-bottom: 12px;
                color: #333;
            }
            .state-view p {
                color: #666;
                line-height: 1.6;
            }
            /* Hide form in success/error states */
            .form-container.hidden {
                display: none;
            }
            .state-view.hidden {
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Campus Device Authorization</h1>
            <p class="subtitle">Enter the code from your CLI application</p>

            <!-- Success State View -->
            <div id="successView" class="state-view {{ 'hidden' if status != 'success' else '' }}" role="alert" aria-live="polite">
                <div class="success-icon"></div>
                <h2>Authorization Complete!</h2>
                <p>Your device has been successfully authorized.</p>
                <p id="successUserId" style="margin-top: 8px; font-weight: 600;"></p>
                <p style="margin-top: 12px;">You can now return to your CLI application.</p>
                <div class="countdown">
                    <span id="countdownText">Returning to your CLI in <span id="countdownTimer">5</span> seconds...</span>
                </div>
                <button type="button" class="btn" id="closeWindowBtn" onclick="attemptClose()" style="margin-top: 16px;">
                    Close Window
                </button>
            </div>

            <!-- Error State View -->
            <div id="errorView" class="state-view {{ 'hidden' if status != 'error' else '' }}" role="alert" aria-live="assertive">
                <div class="error-icon"></div>
                <h2 id="errorTitle">Authorization Failed</h2>
                <p id="errorMessage">An error occurred during authorization.</p>
                <button type="button" class="btn" onclick="location.reload()" style="margin-top: 16px;">
                    Try Again
                </button>
            </div>

            <!-- Form View -->
            <div id="formView" class="form-container {{ 'hidden' if status == 'success' else '' }}">
                <div class="instructions">
                    Your CLI application should have displayed a code.
                    Enter that code below to complete the authentication process.
                </div>

                {% if session_user_id %}
                <div class="identity">
                    Signed in as <strong>{{ session_user_id }}</strong> — this
                    device will be authorized for that account.
                    <a href="{{ logout_url }}">Not you? Sign in as a different user</a>
                </div>
                {% endif %}

                <div id="errorAlert" class="alert error"></div>
                <div id="successAlert" class="alert success"></div>

                <!-- Non-JS fallback for showing query param errors -->
                {% if status == 'error' %}
                <div class="alert error show">
                    {{ error_messages.get(error_code, 'An error occurred during authorization.') }}
                </div>
                {% endif %}

                <form id="authForm" action="{{ url_for('auth.oauth.device_verification') }}" method="POST" onsubmit="handleSubmit(event)">
                    <div class="form-group">
                        <label for="userCode">Enter User Code</label>
                        <input
                            type="text"
                            id="userCode"
                            name="user_code"
                            class="user-code-input"
                            placeholder="XXXX-XXXX"
                            maxlength="9"
                            pattern="[A-Z0-9]{4}-[A-Z0-9]{4}"
                            required
                            {% if safe_user_code %}value="{{ safe_user_code }}"{% endif %}
                        >
                        <input type="hidden" name="redirect_url" value="{{ request.url }}">
                    </div>
                    <button type="submit" class="btn" id="submitBtn">
                        Authorize
                    </button>
                    <noscript>
                        <p style="margin-top: 12px; color: #666; font-size: 13px;">
                            JavaScript is disabled. After clicking Authorize, you will be redirected to see the result.
                        </p>
                    </noscript>
                </form>
            </div>
        </div>

        <script>
            const userCodeInput = document.getElementById('userCode');
            const submitBtn = document.getElementById('submitBtn');
            const errorAlert = document.getElementById('errorAlert');
            const successAlert = document.getElementById('successAlert');
            const formView = document.getElementById('formView');
            const successView = document.getElementById('successView');
            const errorView = document.getElementById('errorView');
            const errorTitle = document.getElementById('errorTitle');
            const errorMessage = document.getElementById('errorMessage');

            // Error messages mapping
            const errorMessages = {
                'invalid_code': 'The user code you entered is invalid. Please check and try again.',
                'expired': 'This user code has expired. Please restart the authentication process on your CLI application to get a new code.',
                'already_used': 'This user code has already been used. Please restart the authentication process on your CLI application to get a new code.',
                'denied': 'The authorization was denied. If you did not intend to deny access, you can restart the process on your CLI application.',
                'not_logged_in': 'You must be logged in to authorize a device. Please log in first.',
                'network_error': 'Network error. Please check your connection and try again.',
                'unknown': 'An unexpected error occurred. Please try again.'
            };

            // Auto-format user code (XXXX-XXXX)
            userCodeInput.addEventListener('input', function(e) {
                let value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
                if (value.length > 4) {
                    value = value.slice(0, 4) + '-' + value.slice(4, 8);
                }
                e.target.value = value;
            });

            async function handleSubmit(e) {
                e.preventDefault();
                const userCode = userCodeInput.value.trim();

                if (!userCode || userCode.length !== 9) {
                    showAlert('error', errorMessages.invalid_code);
                    return;
                }

                // Check if user is logged in
                // Use relative path since /users/me is now under /oauth/
                const response = await fetch('./users/me', {
                    method: 'GET',
                    credentials: 'include'
                });

                if (!response.ok) {
                    showAlert('error', errorMessages.not_logged_in);
                    return;
                }

                const userData = await response.json();
                const userId = userData.user?.id;

                if (!userId) {
                    showAlert('error', errorMessages.not_logged_in);
                    return;
                }

                // Submit the authorization
                submitBtn.disabled = true;
                submitBtn.innerHTML = 'Processing <span class="spinner"></span>';

                try {
                    const authResponse = await fetch('./device/authorize', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        credentials: 'include',
                        body: JSON.stringify({
                            user_code: userCode,
                            user_id: userId
                        })
                    });

                    if (authResponse.ok) {
                        document.getElementById('successUserId').textContent =
                            'Authorized as ' + userId;
                        showSuccessState();
                    } else {
                        const errorData = await authResponse.json();
                        handleError(errorData);
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = 'Authorize';
                    }
                } catch (err) {
                    showAlert('error', errorMessages.network_error);
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = 'Authorize';
                }
            }

            function showAlert(type, message) {
                if (type === 'error') {
                    errorAlert.textContent = message;
                    errorAlert.classList.add('show');
                    successAlert.classList.remove('show');
                } else {
                    successAlert.textContent = message;
                    successAlert.classList.add('show');
                    errorAlert.classList.remove('show');
                }
            }

            function showSuccessState() {
                formView.classList.add('hidden');
                successView.classList.remove('hidden');
                errorView.classList.add('hidden');
                startCountdown();
            }

            function showErrorState(title, message) {
                formView.classList.add('hidden');
                successView.classList.add('hidden');
                errorView.classList.remove('hidden');
                errorTitle.textContent = title;
                errorMessage.textContent = message;
            }

            function handleError(errorData) {
                let message = errorMessages.unknown;
                let stateTitle = 'Authorization Failed';

                if (errorData.error) {
                    const errorCode = errorData.error.state || errorData.error.code;
                    const errorMsg = errorData.error.message || errorData.error.description;

                    if (errorMsg) {
                        message = errorMsg;
                    } else if (errorMessages[errorCode]) {
                        message = errorMessages[errorCode];
                    }

                    if (errorCode === 'expired') {
                        stateTitle = 'Code Expired';
                    } else if (errorCode === 'denied' || errorCode === 'already_used') {
                        stateTitle = 'Authorization Failed';
                    }
                }

                // Show inline alert for quick retries
                showAlert('error', message);

                // Also show error state for severe errors
                if (errorData.error && (errorData.error.state === 'expired' || errorData.error.state === 'denied' || errorData.error.state === 'already_used')) {
                    showErrorState(stateTitle, message);
                }
            }

            function startCountdown() {
                const timer = document.getElementById('countdownTimer');
                const countdownText = document.getElementById('countdownText');
                let seconds = 5;

                // Store interval reference for cleanup
                window.deviceAuthCountdown = setInterval(function() {
                    seconds--;
                    if (timer) timer.textContent = seconds;

                    if (seconds <= 0) {
                        clearInterval(window.deviceAuthCountdown);
                        // window.close() is silently blocked for tabs not opened by
                        // script (device-flow clients open the URL via the OS browser),
                        // so the text swap below is the real user guidance.
                        countdownText.textContent = 'You can safely close this window and return to your CLI application.';
                        window.close();
                    }
                }, 1000);
            }

            function attemptClose() {
                window.close();
                // window.close() does not throw when blocked; if the page is still
                // visible shortly after the call the browser refused the close, so
                // swap the button for guidance text instead of leaving a dead button.
                setTimeout(function() {
                    if (!document.hidden) {
                        document.getElementById('closeWindowBtn').outerHTML =
                            '<p style="margin-top: 16px;">You can close this tab now and return to your CLI application.</p>';
                    }
                }, 150);
            }

            // Auto-focus on the input
            if (userCodeInput && !userCodeInput.disabled) {
                userCodeInput.focus();
            }

            // Pre-filled user code (verification_uri_complete) is NOT
            // auto-submitted: the user must see which account is authorizing
            // and click Authorize themselves (#852 — the auto-submit once
            // bound device grants to whatever SSO session the browser held,
            // with no chance to check).

            // Handle URL-based error states for non-JS redirects
            const urlParams = new URLSearchParams(window.location.search);
            const urlStatus = urlParams.get('status');
            const errorCode = urlParams.get('error_code');

            if (urlStatus === 'success') {
                showSuccessState();
            } else if (urlStatus === 'error' && errorCode) {
                const message = errorMessages[errorCode] || errorMessages.unknown;
                let title = 'Authorization Failed';
                if (errorCode === 'expired') title = 'Code Expired';
                showErrorState(title, message);
            }
        </script>
    </body>
    </html>
    """

    return render_template_string(
        template,
        safe_user_code=safe_user_code,
        status=status,
        error_code=error_code,
        error_messages=error_messages,
        session_user_id=str(user_id) if user_id else None,
        logout_url=logout_url,
    )


@bp.post("/device/authorize")
@unpack_oauth_request
def device_authorize_submit(
        user_code: str,
        user_id: schema.UserID,
) -> flask_campus.JsonResponse:
    """Process the device authorization from the verification page.

    This endpoint is called when a user submits the user code form on the
    verification page. It links the user's account to the pending device code.

    POST /oauth/device/authorize
    Body: {
        "user_code": "ABCD-1234",
        "user_id": "user_123"
    }
    Returns: {
        "success": true
    }

    Error responses return appropriate error codes for the frontend to handle:
    - invalid_code: The user code doesn't exist
    - expired: The user code has expired
    - already_used: The user code has already been used/authorized
    - denied: The authorization was denied
    """
    if not user_code:
        raise api_errors.InvalidRequestError(
            "user_code is required",
            error_code="invalid_code"
        )
    if not user_id:
        raise api_errors.InvalidRequestError(
            "user_id is required",
            error_code="invalid_code"
        )

    try:
        dc = device_code_resource.get_by_user_code(user_code)
    except api_errors.NotFoundError:
        raise api_errors.NotFoundError(
            "Invalid user code. Please check and try again.",
            error_code="invalid_code"
        ) from None

    # Check the state of the device code and provide appropriate error codes
    if dc.state == "expired":
        raise api_errors.ConflictError(
            "This user code has expired. Please restart the authentication process on your CLI application to get a new code.",
            error_code="expired",
            state="expired"
        )
    elif dc.state == "denied":
        raise api_errors.ConflictError(
            "This authorization was previously denied. Please restart the process on your CLI application.",
            error_code="denied",
            state="denied"
        )
    elif dc.state == "authorized":
        raise api_errors.ConflictError(
            "This user code has already been used. Please restart the authentication process on your CLI application to get a new code.",
            error_code="already_used",
            state="authorized"
        )
    elif dc.state != "pending":
        raise api_errors.InternalError(
            f"Invalid device code state: {dc.state}",
            error_code="unknown"
        )

    # Authorize the device code
    device_code_resource.update(
        dc.id,
        user_id=str(user_id),
        state="authorized"
    )

    get_yapper().emit('campus.oauth.device_authorize_submit', {
        "device_code_id": str(dc.id),
        "user_id": str(user_id),
    })

    return {"success": True}, 200


@bp.get("/users/me")
def users_me() -> flask_campus.JsonResponse:
    """Get the current authenticated user from session.

    GET /oauth/users/me
    Returns: User

    This endpoint is used by the device verification page to check if
    the user is authenticated. It returns the user from the Flask session
    without requiring additional authentication headers.
    """
    user_id = flask.session.get('user_id')
    if not user_id:
        raise api_errors.UnauthorizedError(
            "Not authenticated",
            error_code="NOT_AUTHENTICATED"
        )
    return {"user": {"id": str(user_id)}}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with OAuth routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('oauth', __name__, url_prefix='/oauth')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/device_authorize", "device_authorize", device_authorize, methods=["POST"])
    new_bp.add_url_rule("/token", "token", token, methods=["POST"])
    new_bp.add_url_rule("/revoke", "revoke", revoke, methods=["POST"])
    new_bp.add_url_rule("/device", "device_verification", device_verification, methods=["GET", "POST"])
    new_bp.add_url_rule("/device/<user_code>", "device_verification_prefilled", device_verification, methods=["GET", "POST"])
    new_bp.add_url_rule("/device/authorize", "device_authorize_submit", device_authorize_submit, methods=["POST"])
    new_bp.add_url_rule("/users/me", "users_me", users_me, methods=["GET"])

    return new_bp
