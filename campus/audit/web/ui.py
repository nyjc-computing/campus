"""campus.audit.web.ui

UI routes for the Audit Web UI - serves HTML templates for browsing traces.

This module contains web UI routes for the audit service, providing
a web interface for exploring and viewing audit traces.

Page map (docs/web-ui-requirements.md §2):

- GET /audit/ - landing page (public: no login required)
- GET /audit/traces - trace list; ?journey_id=<id> switches it to the
  group-by-journey view (#803) (login required)
- GET /audit/traces/<trace_id> - trace detail (login required)
- GET /audit/journeys/<journey_id> - redirect to the journey view
  (keeps earlier journey URLs working)

The trace list moved from /audit/ to /audit/traces when the landing
page was added; the login gate (campus.audit.web.auth) exempts the
landing page and this blueprint's static assets.
"""

__all__ = ["create_blueprint"]

import flask
import werkzeug


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
