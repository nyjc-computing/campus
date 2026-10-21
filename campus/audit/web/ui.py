"""campus.audit.web.ui

UI routes for the Audit Web UI - serves HTML templates for browsing traces.

This module contains web UI routes for the audit service, providing
a web interface for exploring and viewing audit traces.

Page map (docs/web-ui-requirements.md §2):

- GET / - service root: serves the landing page (campus-wide
  convention, #842: / is a landing page, /health is the health check)
- GET /audit/ - landing page (public: no login required)
- GET /audit/traces - trace list; ?journey_id=<id> switches it to the
  group-by-journey view (#803) (trace-view capability)
- GET /audit/traces/<trace_id> - trace detail (trace-view capability)
- GET /audit/journeys/<journey_id> - redirect to the journey view
  (keeps earlier journey URLs working)

The trace list moved from /audit/ to /audit/traces when the landing
page was added; the login gate (campus.audit.web.auth) exempts the
landing page and this blueprint's static assets.

"Trace-view capability" is the can_view_traces() check of §5.2: a
campus.auth account on the AUDIT_ADMINS superadmin list, or an
API-key session whose key holds traces:read. The sign-in paths live
in campus.audit.web.auth — the OAuth flow, and the paste-key form at
/audit/login/key (development only, #915).
"""

__all__ = ["create_blueprint", "create_root_blueprint"]

import flask
import werkzeug

from . import auth


def create_root_blueprint() -> flask.Blueprint:
    """Create a blueprint serving the service root path / (#842).

    Campus convention: / is a landing page and /health is the health
    check endpoint (registered by campus.deploy). Audit owns / because
    it has a web UI: the landing page is served at both / and /audit/.
    This blueprint is public (no login gate) and only registered for
    standalone deployments (campus.audit init_app on a Flask app).
    """
    bp = flask.Blueprint(
        'audit_root',
        __name__,
        template_folder='templates',
    )

    @bp.get('/')
    def root() -> str:
        """Render the landing page at the service root (#842)."""
        return flask.render_template('index.html')

    return bp


def create_blueprint() -> flask.Blueprint:
    """Create a Flask blueprint for UI routes.

    Returns:
        A Flask blueprint with UI route handlers
    """
    bp = flask.Blueprint(
        'audit_ui',
        __name__,
        url_prefix='/audit',
        template_folder='templates',
        static_folder='static'
    )

    # The shared header (base.html) offers the Keys nav link only to
    # sessions that may manage keys — the same capability the keys page
    # gates on (campus.audit.web.keys). Registered app-wide so every
    # template sees it; anonymous sessions hold nothing, so public
    # pages simply don't show the link.
    @bp.app_context_processor
    def _nav_capabilities() -> dict[str, bool]:
        return {"can_manage_keys": auth.can_manage_keys()}

    @bp.route('/')
    def index() -> str:
        """Render the landing page.

        The landing page is the public entry point for the Audit Web UI:
        it introduces the service and links to the gated trace list and
        the login flow. No trace data is shown here.
        """
        return flask.render_template('index.html')

    @bp.route('/traces')
    def traces() -> str:
        """Render the trace list page (login required via the auth gate).

        Shows the filter bar and trace table; data is loaded client-side
        from the UI data endpoints.
        """
        return flask.render_template('traces.html')

    @bp.route('/traces/<trace_id>')
    def trace(trace_id: str) -> str:
        """Render the trace detail page.

        Shows trace metadata, a span waterfall, and a span details
        drawer; data is loaded client-side from the UI data endpoints.
        """
        return flask.render_template('trace.html', trace_id=trace_id)

    @bp.route('/journeys/<journey_id>')
    def journey(journey_id: str) -> werkzeug.Response:
        """Redirect journey-page links to the merged traces view (#803).

        The journey view is /audit/traces?journey_id=<id>: the same
        trace list switching to group-by-journey. This route keeps any
        previously shared journey URLs working.
        """
        return flask.redirect(
            flask.url_for('audit_ui.traces', journey_id=journey_id)
        )

    return bp
