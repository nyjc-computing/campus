"""campus.audit.web.ui

UI routes for the Audit Web UI - serves HTML templates for browsing traces.

This module contains web UI routes for the audit service, providing
a web interface for exploring and viewing audit traces.
"""

__all__ = ["create_blueprint"]

import flask


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
        """Render the trace list page.

        The list is the main entry point for the Audit Web UI
        (docs/web-ui-requirements.md §2: list at /audit/).
        """
        return flask.render_template('traces.html')

    @bp.route('/traces')
    def traces() -> flask.Response:
        """Redirect the former list URL to /audit/."""
        return flask.redirect(flask.url_for('audit_ui.index'))

    @bp.route('/traces/<trace_id>')
    def trace(trace_id: str) -> str:
        """Render the trace detail page.

        Shows trace metadata, a span waterfall, and a span details
        drawer; data is loaded client-side from the UI data endpoints.
        """
        return flask.render_template('trace.html', trace_id=trace_id)

    return bp
