"""flask_campus.login_manager

OAuth Login Manager for Flask integration.
"""

from functools import wraps
from typing import Callable

import flask
import werkzeug

import campus_python
from campus import flask_campus
from campus.common.utils import url


def _is_safe_redirect(redirect_url: str) -> bool:
    """Ensure URL is safe for redirect (prevents open redirect attacks)."""
    # Only allow relative URLs starting with /
    # Reject protocol-relative URLs (//)
    return redirect_url.startswith('/') and not redirect_url.startswith('//')


def _create_bp(
        campus: campus_python.Campus,
        default_endpoint: str
) -> flask.Blueprint:
    """Create authentication blueprint for Flask app.
    
    Args:
        campus: Campus client instance
        default_endpoint: Default endpoint to redirect to after login/logout
    """
    bp = flask.Blueprint("auth", __name__, url_prefix="/")
    bp.before_request(campus.auth.push_context)

    @bp.get("/login")
    @flask_campus.unpack_request
    def login(next: str | None = None) -> werkzeug.Response:
        """Initiate OAuth login flow.

        Args:
            next: Destination URL to redirect to after successful login

        Returns:
            Redirect to Campus OAuth authorization endpoint
        """
        # Validate and store destination to prevent open redirect attacks
        if next and not _is_safe_redirect(next):
            next = flask.url_for(default_endpoint)
        flask.session['login_next'] = next or flask.url_for(default_endpoint)

        # Use /finalize_login as the OAuth callback
        # Use url.full_url_for to get proper public URL (not localhost/internal host)
        callback_url = url.full_url_for('auth.finalize_login')
        return campus.auth.authorize(target=callback_url)


    @bp.get("/finalize_login")
    @flask_campus.unpack_request
    def finalize_login(
            code: str,
            state: str,
            scope: str
    ) -> werkzeug.Response:
        """OAuth callback endpoint - completes authentication.

        This is the registered callback URL for Campus OAuth flows.

        Steps:
        1. Validates the auth session
        2. Exchanges authorization code for access token
        3. Stores credentials automatically via token endpoint
        4. Creates login session (30-day expiry)
        5. Redirects to the user's intended destination

        Args:
            code: Authorization code from OAuth provider
            state: Session state for CSRF protection
            scope: Granted OAuth scopes

        Returns:
            Redirect to the destination stored in login_next session variable
        """
        # Complete the OAuth flow (creates login session)
        campus.auth.finalize(state=state, code=code, scope=scope)
        campus.auth.push_context()

        # Redirect to the original destination
        next_url = flask.session.pop('login_next', '/')
        return flask.redirect(next_url)

    @bp.get("/logout")
    def logout():
        """Sign Out of Campus Admin Portal."""
        campus.auth.logout()
        resp = flask.redirect(flask.url_for(default_endpoint))
        return resp

    return bp


class OAuthLoginManager:
    """OAuth Login Manager for Flask integration."""

    def __init__(
            self,
            campus_client: campus_python.Campus | None = None,
            default_endpoint: str = "index"
    ):
        """Initialize the OAuthLoginManager.

        Args:
            campus_client: Optional Campus client instance. If None, a
                new instance will be created.
            default_endpoint: Default endpoint to redirect to after login/logout
        """
        self.campus = campus_client or campus_python.Campus(timeout=60)
        self.default_endpoint = default_endpoint

    def init_app(self, app: flask.Flask | flask.Blueprint):
        """Initialize the login manager with the Flask app."""
        bp = _create_bp(self.campus, self.default_endpoint)
        app.register_blueprint(bp)
        if isinstance(app, flask.Flask):
            app.before_request(self.campus.auth.push_context)
        elif isinstance(app, flask.Blueprint):
            app.before_app_request(self.campus.auth.push_context)

    def login_required(self, view: Callable) -> Callable:
        """Decorator to protect routes that require authentication."""
        @wraps(view)
        def wrapped_view(**kwargs):
            if not hasattr(flask.g, "user") or flask.g.user is None:
                return flask.redirect(
                    flask.url_for('auth.login', next=flask.request.path)
                )
            return view(**kwargs)
        return wrapped_view
