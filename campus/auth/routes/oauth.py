"""campus.auth.routes.oauth

Flask routes for OAuth 2.0 Device Authorization Flow (RFC 8628).

These routes handle device authorization for CLI and other device applications.

These routes do NOT require authentication - they are publicly accessible
for the device authorization flow to work.
"""

import flask

import campus.config
import campus.model
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors, auth_errors, token_errors
from campus.common.utils import uid, secret

from .. import get_yapper
from ..resources import device_code as device_code_resource
from ..resources import client as client_resource
from ..resources import credentials as credentials_resource

# Create blueprint for OAuth routes
bp = flask.Blueprint('oauth', __name__, url_prefix='/oauth')

# Default scopes for CLI clients
DEFAULT_CLI_SCOPES = ["read", "write"]


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
) -> flask_campus.JsonResponse:
    """Request a device code for OAuth 2.0 Device Authorization Flow.

    POST /oauth/device_authorize
    Body: {
        "client_id": "guest"
    }
    Returns: {
        "device_code": "...",
        "user_code": "ABCD-1234",
        "verification_uri": "https://auth.campus.nyjc.app/device",
        "verification_uri_complete": "https://auth.campus.nyjc.app/device?user_code=ABCD-1234",
        "expires_in": 600,
        "interval": 5
    }

    Reference: https://datatracker.ietf.org/doc/html/rfc8628#section-3.1
    """
    # Validate the client
    # "guest" is a special public client type for CLI/device apps
    # It doesn't exist in the database and has no inherent permissions
    # All access comes from the user's credentials during the OAuth flow
    if client_id == campus.config.PUBLIC_OAUTH_CLIENT_ID:
        # Skip database validation for public guest clients
        pass
    else:
        # For regular clients, verify they exist in the database
        try:
            client_resource[client_id].get()
        except api_errors.NotFoundError:
            raise token_errors.InvalidClientError(
                "Invalid client_id"
            )

    # Create device code
    device_code = device_code_resource.create(
        client_id=client_id,
        scopes=DEFAULT_CLI_SCOPES,
    )

    # Build verification URIs
    # Use the request to determine the base URL
    # Note: endpoint needs 'auth.' prefix since oauth blueprint is registered under auth blueprint
    verification_uri = flask.url_for(
        "auth.oauth.device_verification",
        _external=True
    )
    verification_uri_complete = flask.url_for(
        "auth.oauth.device_verification",
        _external=True,
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
        device_code: str | None = None,
        code: str | None = None,
        redirect_uri: str | None = None,
        refresh_token: str | None = None,
) -> flask_campus.JsonResponse:
    """Exchange an authorization grant for an access token.

    Supports multiple grant types:
    - urn:ietf:params:oauth:grant-type:device_code (RFC 8628)
    - authorization_code (RFC 6749)
    - refresh_token (RFC 6749)

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
    Returns: {
        "access_token": "...",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "...",
        "scope": "read write"
    }
    """
    # Validate the client
    # "guest" is a special public client type - no database validation needed
    if client_id != campus.config.PUBLIC_OAUTH_CLIENT_ID:
        try:
            client_resource[client_id].get()
        except api_errors.NotFoundError:
            raise token_errors.InvalidClientError(
                "Invalid client_id"
            )

    # Route to appropriate handler based on grant_type
    if grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        return _handle_device_code_grant(client_id, device_code)
    elif grant_type == "authorization_code":
        return _handle_authorization_code_grant(client_id, code, redirect_uri)
    elif grant_type == "refresh_token":
        return _handle_refresh_token_grant(client_id, refresh_token)
    else:
        raise token_errors.UnsupportedGrantTypeError(
            f"Unsupported grant_type: {grant_type}"
        )


def _handle_device_code_grant(
        client_id: schema.CampusID,
        device_code: str | None,
) -> flask_campus.JsonResponse:
    """Handle the device_code grant type."""
    if not device_code:
        raise token_errors.InvalidRequestError(
            "device_code is required for device_code grant type"
        )

    try:
        dc = device_code_resource.get_by_device_code(device_code)
    except api_errors.NotFoundError:
        raise token_errors.InvalidGrantError(
            "Invalid or expired device code"
        )

    # Check the state of the device code
    if dc.state == "pending":
        # User hasn't completed auth yet
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

        # Create OAuth token
        access_token = secret.generate_access_token()
        refresh_tok = secret.generate_access_code()

        # Calculate expiry
        created_at = schema.DateTime.utcnow()
        expiry_seconds = campus.config.DEFAULT_TOKEN_EXPIRY_DAYS * 24 * 60 * 60

        # Create OAuthToken model
        oauth_token = campus.model.OAuthToken(
            id=access_token,
            created_at=created_at,
            expiry_seconds=expiry_seconds,
            refresh_token=refresh_tok,
            scopes=dc.scopes,
        )

        try:
            # Store credentials using the resource
            credentials_resource["campus"][dc.user_id].update(
                client_id=str(client_id),
                token=oauth_token,
            )
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)

        # Delete the device code as it's now used
        device_code_resource.delete(dc.id)

        get_yapper().emit('campus.oauth.token', {
            "grant_type": "device_code",
            "client_id": str(client_id),
            "user_id": str(dc.user_id),
        })

        # Return token response
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": campus.config.DEFAULT_TOKEN_EXPIRY_DAYS * 24 * 60 * 60,
            "refresh_token": refresh_tok,
            "scope": " ".join(dc.scopes),
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
    """Handle the refresh_token grant type."""
    if not refresh_token:
        raise token_errors.InvalidRequestError(
            "refresh_token is required for refresh_token grant type"
        )

    # Find credentials by refresh token
    # This requires additional implementation
    raise token_errors.UnsupportedGrantTypeError(
        "refresh_token grant not yet implemented"
    )


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
    from flask import render_template_string, request, redirect
    import html

    # Handle POST for non-JS fallback
    if request.method == "POST":
        user_code_form = request.form.get('user_code', '').strip().upper()
        redirect_url = request.form.get('redirect_url', flask.url_for('auth.oauth.device_verification', _external=True))

        # Validate user code format
        if not user_code_form or len(user_code_form) != 9 or user_code_form[4] != '-':
            return redirect(f"{redirect_url}?status=error&error_code=invalid_code")

        # Get user ID from session (user must be logged in)
        from flask import session
        user_id = session.get('user_id')
        if not user_id:
            return redirect(f"{redirect_url}?status=error&error_code=not_logged_in")

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
                <p style="margin-top: 12px;">You can now return to your CLI application.</p>
                <div class="countdown">
                    <span id="countdownText">This window will close in <span id="countdownTimer">5</span> seconds...</span>
                </div>
                <button type="button" class="btn" onclick="window.close()" style="margin-top: 16px;">
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
                            {{ 'value="' + safe_user_code + '"' if safe_user_code else '' }}
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
                const response = await fetch('/api/v1/users/me', {
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
                    const authResponse = await fetch('/api/v1/oauth/device/authorize', {
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
                        countdownText.textContent = 'Closing window...';
                        setTimeout(function() {
                            window.close();
                        }, 500);
                    }
                }, 1000);
            }

            // Auto-focus on the input
            if (userCodeInput && !userCodeInput.disabled) {
                userCodeInput.focus();
            }

            // Pre-filled user code - auto-submit if valid
            {{ 'if (userCodeInput.value.length === 9) { submitBtn.click(); }' if user_code and status != 'success' and status != 'error' else '' }}

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
        )

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


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with OAuth routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('oauth', __name__, url_prefix='/oauth')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/device_authorize", "device_authorize", device_authorize, methods=["POST"])
    new_bp.add_url_rule("/token", "token", token, methods=["POST"])
    new_bp.add_url_rule("/device", "device_verification", device_verification, methods=["GET", "POST"])
    new_bp.add_url_rule("/device/<user_code>", "device_verification_prefilled", device_verification, methods=["GET", "POST"])
    new_bp.add_url_rule("/device/authorize", "device_authorize_submit", device_authorize_submit, methods=["POST"])

    return new_bp
